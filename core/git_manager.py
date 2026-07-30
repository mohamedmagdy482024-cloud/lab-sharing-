import subprocess
import os
import json
import time
import socket
import shutil
from core.logger import logger
from core.platform import detached_process_kwargs, git_daemon_base_path, terminate_process

GIT_CONFIG_FILE = os.path.expanduser("~/.lab-sharing/git_config.json")
PID_FILE        = os.path.expanduser("~/.lab-sharing/daemon.pid")
LOG_FILE        = os.path.expanduser("~/.lab-sharing/daemon.log")
REPOS_DIR       = os.path.expanduser("~/.lab-sharing/repos")


# ── helpers ──────────────────────────────────────────────────────────────────

def _clean_path(p: str | None) -> str:
    """Strip all leading/trailing whitespace from a filesystem path."""
    if not p:
        return p or ""
    return p.strip()


def _sanitize_name(path):
    """Convert any path to a safe name for git daemon (no spaces/brackets)"""
    name = os.path.basename(_clean_path(path).rstrip("/"))
    for ch in [" ", "(", ")", "[", "]", "&", "'"]:
        name = name.replace(ch, "_")
    return name.strip("_") or "repo"


def resolve_case_insensitive_path(path):
    if os.path.exists(path):
        return path
    parts = path.strip("/").split("/")
    current = "/" if path.startswith("/") else ""
    for part in parts:
        if not part: continue
        next_path = os.path.join(current, part)
        if os.path.exists(next_path):
            current = next_path
        else:
            try:
                files = os.listdir(current or ".")
            except OSError:
                return path
            found = False
            for f in files:
                if f.lower().strip() == part.lower().strip():
                    current = os.path.join(current, f)
                    found = True
                    break
            if not found:
                return path
    return current


def _run(cmd, cwd=None, timeout=30, silent=False):
    """Run a git command, return (success, output)"""
    try:
        result = subprocess.run(
            cmd, cwd=cwd,
            capture_output=True, text=True,
            timeout=timeout
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        ok  = result.returncode == 0
        if err and not ok and not silent:
            logger.error(f"git error: {err}")
        
        # Combine stdout and stderr. 
        # Previously, if stdout was not empty, stderr was completely dropped in the return value.
        # This caused us to miss merge errors that print success-like info to stdout and errors to stderr.
        combined = f"{out}\n{err}".strip() if (out and err) else (out or err)
        return ok, combined
    except subprocess.TimeoutExpired:
        logger.error(f"git command timed out: {cmd}")
        return False, "Command timed out"
    except Exception as e:
        logger.error(f"git command failed: {e}")
        return False, str(e)


# ── config ───────────────────────────────────────────────────────────────────

def save_config(
    role,
    repo_path,
    remote_ip=None,
    safe_name=None,
    server_repo_path=None,
    default_branch=None,
    auto_pull=None,
    server_mirror_path=None,
):
    os.makedirs(os.path.dirname(GIT_CONFIG_FILE), exist_ok=True)
    existing = load_config() or {}
    real_path = os.path.realpath(resolve_case_insensitive_path(_clean_path(repo_path)))
    config = {
        "role":             role,
        "repo_path":        real_path,
        "remote_ip":        remote_ip if remote_ip is not None else existing.get("remote_ip"),
        "safe_name":        _clean_path(safe_name) or _clean_path(existing.get("safe_name")) or _sanitize_name(real_path),
        "server_repo_path": (
            _clean_path(server_repo_path) if server_repo_path
            else existing.get("server_repo_path")
        ),
        "default_branch":   default_branch or existing.get("default_branch") or "main",
        "auto_pull":        auto_pull if auto_pull is not None else existing.get("auto_pull", "off"),
        "server_mirror_path": (
            _clean_path(server_mirror_path) if server_mirror_path
            else existing.get("server_mirror_path")
        ),
    }
    with open(GIT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    logger.info(f"Config saved: role={role}, repo={real_path}, branch={config['default_branch']}")


def load_config():
    if not os.path.exists(GIT_CONFIG_FILE):
        return None
    try:
        with open(GIT_CONFIG_FILE) as f:
            cfg = json.load(f)
        
        # Heal config paths FIRST, before stripping here, so that heal_config_paths
        # sees the raw values with trailing spaces and can rename folders on disk.
        cfg = heal_config_paths(cfg)
        
        if cfg.get("repo_path"):
            cfg["repo_path"] = _clean_path(cfg["repo_path"])
        if cfg.get("server_repo_path"):
            cfg["server_repo_path"] = _clean_path(cfg["server_repo_path"])
        if cfg.get("server_mirror_path"):
            cfg["server_mirror_path"] = _clean_path(cfg["server_mirror_path"])
        if cfg.get("safe_name"):
            cfg["safe_name"] = _clean_path(cfg["safe_name"])
            
        return migrate_config(cfg)
    except Exception:
        return None


def migrate_config(cfg):
    """Fill missing keys for configs saved before newer features."""
    if not cfg:
        return cfg
    changed = False
    repo = cfg.get("repo_path")
    if not cfg.get("default_branch") and repo and os.path.isdir(repo):
        cfg["default_branch"] = get_current_branch(repo)
        changed = True
    if cfg.get("auto_pull") is None:
        cfg["auto_pull"] = "off"
        changed = True
    if cfg.get("role") == "main" and cfg.get("server_repo_path"):
        if not cfg.get("server_mirror_path"):
            cfg["server_mirror_path"] = get_server_mirror_path(cfg)
            changed = True
    if changed:
        persist_config(cfg)
    return cfg


def heal_config_paths(cfg: dict) -> dict:
    """
    Detect and silently fix trailing/leading spaces in all saved paths.
    If a folder exists on disk under the dirty name but not the clean name,
    rename it automatically.
    Also fixes the git remote URL in the working repo if it still points
    to a dirty (trailing-space) path.
    Called every time the config is loaded.
    Returns the cleaned config dict.
    """
    if not cfg:
        return cfg

    changed = False
    dirty_server = cfg.get("server_repo_path", "")  # remember original before cleaning

    path_keys = ["repo_path", "server_repo_path", "server_mirror_path"]
    for key in path_keys:
        raw = cfg.get(key)
        if raw and raw != raw.strip():
            clean = raw.strip()
            logger.warning(
                f"[heal] '{key}' had leading/trailing space: {raw!r} \u2192 {clean!r}"
            )
            # Rename folder on disk if dirty name exists but clean name doesn't
            if os.path.exists(raw) and not os.path.exists(clean):
                try:
                    os.rename(raw, clean)
                    logger.info(f"[heal] Renamed on disk: {raw!r} \u2192 {clean!r}")
                except OSError as e:
                    logger.error(f"[heal] Could not rename {raw!r}: {e}")
                    clean = raw  # keep original if rename failed
            cfg[key] = clean
            changed = True

    raw_name = cfg.get("safe_name")
    if raw_name and raw_name != raw_name.strip():
        cfg["safe_name"] = raw_name.strip()
        logger.warning(f"[heal] 'safe_name' cleaned: {raw_name!r} \u2192 {cfg['safe_name']!r}")
        changed = True

    if changed:
        # Write JSON directly to avoid calling save_config->load_config->heal infinite loop
        os.makedirs(os.path.dirname(GIT_CONFIG_FILE), exist_ok=True)
        with open(GIT_CONFIG_FILE, "w", encoding="utf-8") as f:
            import json as _json
            _json.dump(cfg, f, indent=2)
        logger.info("[heal] Config re-saved with clean paths.")

        # Fix the git remote URL in the working repo if it still points to the dirty path
        repo_path = cfg.get("repo_path")
        clean_server = cfg.get("server_repo_path")
        if repo_path and clean_server and dirty_server and dirty_server != clean_server:
            if os.path.isdir(os.path.join(repo_path, ".git")):
                try:
                    import subprocess as _sp
                    result = _sp.run(
                        ["git", "remote", "get-url", "origin"],
                        cwd=repo_path, capture_output=True, text=True
                    )
                    current_url = result.stdout.strip()
                    if current_url == dirty_server:
                        _sp.run(
                            ["git", "remote", "set-url", "origin", clean_server],
                            cwd=repo_path, capture_output=True
                        )
                        logger.info(
                            f"[heal] Git remote updated: {dirty_server!r} \u2192 {clean_server!r}"
                        )
                except Exception as e:
                    logger.warning(f"[heal] Could not fix git remote: {e}")

    return cfg


def persist_config(cfg):
    """Write config dict back to disk (after migrate)."""
    if not cfg or not cfg.get("repo_path"):
        return
    save_config(
        cfg["role"],
        cfg["repo_path"],
        remote_ip=cfg.get("remote_ip"),
        safe_name=cfg.get("safe_name"),
        server_repo_path=cfg.get("server_repo_path"),
        default_branch=cfg.get("default_branch"),
        auto_pull=cfg.get("auto_pull"),
        server_mirror_path=cfg.get("server_mirror_path"),
    )


def is_git_repo(path):
    """Check if path is a git repo (normal or bare)"""
    p = _clean_path(path)
    # Normal repo has .git/ dir
    if os.path.exists(os.path.join(p, ".git")):
        return True
    # Bare repo has HEAD file directly
    if os.path.isfile(os.path.join(p, "HEAD")):
        return True
    return False


def is_bare_repo(path):
    """True only for a bare repository (server-side history store)."""
    p = _clean_path(path)
    if not is_git_repo(p):
        return False
    ok, out = _run(["git", "rev-parse", "--is-bare-repository"], cwd=p)
    return ok and out.strip().lower() == "true"


def explain_push_error(output: str) -> str | None:
    """Return a short user-facing hint for common push failures."""
    low = (output or "").lower()
    if "denycurrentbranch" in low or "checked out branch" in low:
        return (
            "Server folder is not a bare repository.\n"
            "Restart the app to auto-repair, or Git Sync → Set as Main Device again."
        )
    return None


def _convert_server_to_bare(server_repo, repo_path):
    """
    Replace a normal (non-bare) server folder with a bare clone of the working repo.
    The old server folder is renamed to <name>.__lab_old_nonbare__
    Returns (ok, backup_path_or_error_message).
    """
    server_repo = os.path.realpath(server_repo)
    repo_path   = os.path.realpath(repo_path)

    # Guard: working repo must exist and be a valid git repo before cloning from it.
    # If not, fail clearly instead of crashing on a missing path.
    if not os.path.isdir(repo_path):
        return False, (
            f"Working folder does not exist on disk: {repo_path}\n"
            "Cannot build bare server from it — check the path in Git Sync settings."
        )
    if not is_git_repo(repo_path):
        return False, (
            f"Working folder is not a git repo: {repo_path}\n"
            "Initialise it first (Set as Main Device) before repairing the server folder."
        )

    if os.path.normcase(server_repo) == os.path.normcase(repo_path):
        return False, "Server and working folders must be different paths."

    parent   = os.path.dirname(server_repo)
    name     = os.path.basename(server_repo)
    temp_bare = os.path.join(parent, name + ".__lab_bare_tmp__")
    backup    = os.path.join(parent, name + ".__lab_old_nonbare__")

    if os.path.exists(temp_bare):
        shutil.rmtree(temp_bare, ignore_errors=True)

    logger.info(f"Building bare server repo from working copy: {repo_path}")
    ok, out = _run(["git", "clone", "--bare", repo_path, temp_bare])
    if not ok:
        return False, f"Could not create bare repo: {out}"

    if os.path.exists(backup):
        shutil.rmtree(backup, ignore_errors=True)

    if os.path.exists(server_repo):
        try:
            os.rename(server_repo, backup)
        except OSError as e:
            shutil.rmtree(temp_bare, ignore_errors=True)
            return False, (
                f"Could not backup old server folder (close files/OneDrive sync): {e}"
            )

    try:
        os.rename(temp_bare, server_repo)
    except OSError as e:
        if os.path.exists(backup) and not os.path.exists(server_repo):
            os.rename(backup, server_repo)
        shutil.rmtree(temp_bare, ignore_errors=True)
        return False, f"Could not install bare repo: {e}"

    export_file = os.path.join(server_repo, "git-daemon-export-ok")
    open(export_file, "w").close()
    logger.info(f"Server folder is now bare. Old copy backed up to: {backup}")
    return True, backup


def repair_server_bare_if_needed(config):
    """
    If the configured server path is a normal repo, convert it to bare and
    re-sync the working copy's origin. Returns (ok, message).
    """
    if not config or config.get("role") != "main":
        return True, "Not main role"
    repo_path = config.get("repo_path")
    server_repo = get_bare_repo_path(config)
    if not repo_path or not server_repo:
        return False, "Missing working or server path in config"
    repo_path = os.path.realpath(repo_path)
    server_repo = os.path.realpath(server_repo)
    if is_bare_repo(server_repo):
        return True, "Server is already bare"
    ok, msg = _convert_server_to_bare(server_repo, repo_path)
    if not ok:
        return False, msg
    ok_r, remotes = _run(["git", "remote"], cwd=repo_path)
    if ok_r and "origin" in remotes.split():
        _run(["git", "remote", "remove", "origin"], cwd=repo_path)
    _run(["git", "remote", "add", "origin", server_repo], cwd=repo_path)
    branch = get_current_branch(repo_path)
    ok_push, push_out = _run(["git", "push", "-u", "origin", branch], cwd=repo_path)
    if ok_push:
        return True, f"Server repaired (bare). Old folder: {msg}"
    return True, (
        f"Server converted to bare (backup: {msg}) but push needs retry: {push_out}"
    )


def get_current_branch(repo_path):
    """Return the active branch name, or a sensible default."""
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    ok, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    if ok and branch.strip() and branch.strip() != "HEAD":
        return branch.strip()
    return "main"


def get_bare_repo_path(config):
    """
    Absolute path to the Main device's bare server repo from saved config.
    Returns None for clients or if paths cannot be resolved.
    """
    if not config or config.get("role") != "main":
        return None
    repo_path = config.get("repo_path")
    server_repo_path = config.get("server_repo_path")
    if server_repo_path and _clean_path(server_repo_path):
        return os.path.realpath(_clean_path(server_repo_path))
    if not repo_path:
        return None
    base_dir, safe_name = _get_server_repo_path(
        repo_path, config.get("safe_name"), None)
    return os.path.join(base_dir, safe_name)


def verify_published(repo_path, bare_path=None):
    """
    After a push, check that the server has the same commit as the working repo.
    Main: pass bare_path to the bare repository directory.
    Client: bare_path=None — compares HEAD to origin/<branch> after fetch.
    Returns (ok, message).
    """
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    branch = get_current_branch(repo_path)
    ok_w, head = _run(["git", "rev-parse", "HEAD"], cwd=repo_path)
    if not ok_w or not head:
        return False, "Could not read working repository HEAD"

    if bare_path:
        bare_path = os.path.realpath(bare_path)
        if not is_bare_repo(bare_path):
            return False, (
                f"Server path is not a bare repo: {bare_path}\n"
                "Reset Git setup and choose a dedicated empty server folder."
            )
        ok_b, server_head = _run(["git", "rev-parse", branch], cwd=bare_path)
    else:
        _run(["git", "fetch", "origin"], cwd=repo_path, silent=True)
        ok_b, server_head = _run(
            ["git", "rev-parse", f"origin/{branch}"], cwd=repo_path)

    if not ok_b or not server_head:
        return False, f"Could not read server ref for branch '{branch}'"

    server_head = server_head.strip()
    if head == server_head:
        return True, f"Published to server @ {head[:8]}"
    return False, (
        f"Server NOT updated — working {head[:8]} vs server {server_head[:8]}"
    )


def get_server_mirror_path(config):
    """Folder where latest server files are checked out for browsing (Phase 6)."""
    if not config:
        return None
    custom = config.get("server_mirror_path")
    if custom and _clean_path(custom):
        return os.path.realpath(_clean_path(custom))
    bare = get_bare_repo_path(config)
    if not bare:
        return None
    return os.path.realpath(bare + "_files")


def update_server_mirror(config, branch=None):
    """
    After push, export bare repo into a normal folder (like GitHub file view).
    Returns (ok, message).
    """
    bare = get_bare_repo_path(config)
    mirror = get_server_mirror_path(config)
    if not bare or not mirror:
        return False, "No server or mirror path configured"
    if not is_bare_repo(bare):
        return False, "Server is not bare — skip mirror"
    branch = branch or config.get("default_branch") or get_current_branch(
        config.get("repo_path", bare))
    os.makedirs(mirror, exist_ok=True)
    ok, out = _run(
        [
            "git",
            f"--git-dir={bare}",
            f"--work-tree={mirror}",
            "checkout",
            "-f",
            branch,
        ],
        timeout=60,
    )
    if ok:
        logger.info(f"Server mirror updated: {mirror} @ {branch}")
        return True, f"Server files mirror updated: {mirror}"
    return False, f"Mirror update failed: {out}"


def get_configured_branch(config, repo_path=None):
    if config and config.get("default_branch"):
        return config["default_branch"]
    if repo_path:
        return get_current_branch(repo_path)
    return "main"


# ── symlink ───────────────────────────────────────────────────────────────────

def _get_server_repo_path(repo_path, custom_safe_name=None, custom_server_path=None):
    """Return the base dir and safe name for the server bare repo"""
    # If user provided a full custom server path, use it directly
    if custom_server_path and _clean_path(custom_server_path):
        clean_path = os.path.normpath(_clean_path(custom_server_path))
        full = os.path.realpath(clean_path)
        base_dir = os.path.dirname(full)
        safe_name = _clean_path(os.path.basename(full))
        
        return base_dir, safe_name

    real_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    if custom_safe_name:
        safe_name = custom_safe_name
        if not safe_name.endswith(".git"):
            safe_name += ".git"
    else:
        safe_name = _sanitize_name(real_path) + ".git"
    os.makedirs(REPOS_DIR, exist_ok=True)
    return REPOS_DIR, safe_name


# ── repo init ─────────────────────────────────────────────────────────────────

def init_main_repo(repo_path, custom_safe_name=None, server_repo_path=None):
    """Initialize the main repo. 
    repo_path: working folder where user edits files.
    server_repo_path: optional full path for the bare server repo.
    """
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    logger.info(f"=== INIT MAIN REPO: {repo_path} ===")

    if not os.path.exists(repo_path):
        return False, f"Path does not exist: {repo_path}"

    base_dir, safe_name = _get_server_repo_path(repo_path, custom_safe_name, server_repo_path)
    
    if server_repo_path and _clean_path(server_repo_path):
        server_repo = os.path.realpath(_clean_path(server_repo_path))
    else:
        server_repo = os.path.join(base_dir, safe_name)

    # 2. Initialize Working Repo first so we can detect its branch
    if not is_git_repo(repo_path):
        ok, out = _run(["git", "init"], cwd=repo_path)
        logger.info(f"git init working dir: {out}")
    else:
        logger.info("Working repo already initialized")

    # Detect the actual branch in the working folder
    ok_b, actual_branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    actual_branch = actual_branch.strip() if (ok_b and actual_branch.strip() and actual_branch.strip() != "HEAD") else "master"
    logger.info(f"Working folder branch detected: {actual_branch}")

    # 1. Initialize Server Bare Repo (using the actual branch name)
    if is_git_repo(server_repo):
        if not is_bare_repo(server_repo):
            ok_conv, conv_msg = _convert_server_to_bare(server_repo, repo_path)
            if not ok_conv:
                return False, (
                    "Server folder is a normal Git project, not a bare server repo.\n\n"
                    + str(conv_msg)
                    + "\n\nOr create a new empty server folder and use Git Sync → Reset."
                )
            logger.info(f"Converted server to bare repo (backup: {conv_msg})")
        _run(["git", "symbolic-ref", "HEAD", f"refs/heads/{actual_branch}"], cwd=server_repo)
        logger.info(f"Bare repo HEAD synced to: {actual_branch}")
    else:
        os.makedirs(server_repo, exist_ok=True)
        ok, out = _run(["git", "init", "--bare", f"--initial-branch={actual_branch}"], cwd=server_repo)
        if not ok:
            return False, f"Failed to create bare server repo: {out}"
        logger.info(f"Init bare repo: {out}")
        export_file = os.path.join(server_repo, "git-daemon-export-ok")
        open(export_file, "w").close()

    ok, name = _run(["git", "config", "user.name"], cwd=repo_path)
    if not ok or not name:
        _run(["git", "config", "user.name", socket.gethostname()], cwd=repo_path)
        _run(["git", "config", "user.email", "lab@sharing.local"], cwd=repo_path)

    # 3. Add remote origin to Working Repo pointing to Server Repo
    ok, remotes = _run(["git", "remote"], cwd=repo_path)
    if "origin" in remotes.split():
        _run(["git", "remote", "remove", "origin"], cwd=repo_path)
    
    _run(["git", "remote", "add", "origin", server_repo], cwd=repo_path)
    
    # export-ok (ensure it exists for bare repos)
    export_file = os.path.join(server_repo, "git-daemon-export-ok")
    if not os.path.exists(export_file):
        open(export_file, "w").close()
    
    # Create default .gitignore if missing
    gitignore_path = os.path.join(repo_path, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w") as f:
            f.write("*.pyc\n__pycache__/\nbuild/\ndist/\n*.o\n*.obj\n.env\n")
        logger.info("Created default .gitignore")

    # 4. Initial commit if no commits yet
    ok, log = _run(["git", "log", "--oneline", "-1"], cwd=repo_path)
    if not ok or not log:
        _run(["git", "add", "."], cwd=repo_path)
        ok, out = _run(["git", "commit", "-m", "Initial commit — Lab Sharing"], cwd=repo_path)
        if ok:
            logger.info(f"Initial commit: {out}")
        else:
            logger.info("No files to commit yet — repo is empty")
    
    # 5. Push to server repo using the detected actual branch
    ok_push, push_out = _initial_push_to_bare(repo_path, server_repo, actual_branch)
    if ok_push:
        logger.info(f"Pushed {actual_branch} to server repo ✅")
    else:
        logger.error(f"Push to server repo failed: {push_out}")
        hint = explain_push_error(push_out)
        if hint:
            return False, hint
        return False, f"Push to server repo failed: {push_out}"

    mirror_cfg = {
        "role": "main",
        "repo_path": repo_path,
        "server_repo_path": server_repo,
        "default_branch": actual_branch,
    }
    ok_m, msg_m = update_server_mirror(mirror_cfg, actual_branch)
    if ok_m:
        logger.info(msg_m)

    return True, "Main repo ready ✅"


def _bare_branch_has_commits(bare_path, branch):
    """True if the bare repo already has at least one commit on branch."""
    ok, out = _run(["git", "rev-parse", branch], cwd=bare_path)
    return ok and bool(out.strip())


def _initial_push_to_bare(repo_path, bare_path, branch):
    """
    Push working repo to bare on setup.
    Uses a normal push first; never force-overwrites existing bare history.
    """
    if _bare_branch_has_commits(bare_path, branch):
        ok_push, push_out = _run(
            ["git", "push", "-u", "origin", branch], cwd=repo_path)
        if ok_push:
            return True, push_out
        logger.warning(
            f"Bare repo already has history; push rejected: {push_out}")
        return False, (
            f"Server repo already has commits and push was rejected. "
            f"Pull or merge manually, or use a fresh bare folder. ({push_out})"
        )
    return _run(["git", "push", "-u", "origin", branch], cwd=repo_path)


# ── daemon ────────────────────────────────────────────────────────────────────

def is_daemon_running():
    """
    Check if git daemon is running AND responding.
    Tests actual connection, not just PID.
    """
    try:
        # Quick TCP check on port 9418
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(("127.0.0.1", 9418))
        s.close()
        return result == 0  # 0 = port is open = daemon running
    except Exception:
        return False


def start_git_daemon(repo_path, custom_safe_name=None, server_repo_path=None):
    """
    Start git daemon. Restarts if base path changes.
    Returns (proc, port, safe_name)
    """
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    base_dir, safe_name = _get_server_repo_path(repo_path, custom_safe_name, server_repo_path)
    
    safe_name = safe_name.strip()
    if " " in safe_name:
        logger.warning(f"[daemon] safe_name '{safe_name}' contains spaces — replacing with '_'")
        safe_name = safe_name.replace(" ", "_")

    if server_repo_path and _clean_path(server_repo_path):
        server_repo = os.path.realpath(_clean_path(server_repo_path))
    else:
        server_repo = os.path.join(base_dir, safe_name)
    if os.path.exists(server_repo):
        export_file = os.path.join(server_repo, "git-daemon-export-ok")
        if not os.path.exists(export_file):
            try:
                open(export_file, "w").close()
            except Exception as e:
                logger.error(f"Failed to create export-ok: {e}")

    # Stop any existing daemon to ensure it uses the new base_dir
    stop_git_daemon()

    logger.info(f"Starting git daemon — base: {base_dir}, repo: {safe_name}")
    try:
        daemon_base = git_daemon_base_path(base_dir)
        with open(LOG_FILE, "w") as lf:
            proc = subprocess.Popen(
                [
                    "git", "daemon",
                    "--reuseaddr",
                    f"--base-path={daemon_base}",
                    "--export-all",
                    "--enable=receive-pack",
                    "--enable=upload-pack",
                    "--verbose",
                    "--port=9418"
                ],
                stdout=lf,
                stderr=lf,
                **detached_process_kwargs(),
            )

        # Save PID
        with open(PID_FILE, "w") as pf:
            pf.write(str(proc.pid))

        # Wait and verify
        for i in range(5):
            time.sleep(0.8)
            if is_daemon_running():
                logger.info(f"✅ Git daemon started — PID: {proc.pid}, clone name: {safe_name}")
                return proc, 9418, safe_name

        logger.error("Git daemon started but not responding on port 9418")
        return proc, 9418, safe_name

    except Exception as e:
        logger.error(f"Git daemon error: {e}")
        return None, None, safe_name


def stop_git_daemon():
    """Kill git daemon started by this app (PID file only — no global pkill)."""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            try:
                terminate_process(pid)
                time.sleep(0.5)
            except (ProcessLookupError, OSError):
                pass
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
        logger.info("Git daemon stopped")
    except Exception as e:
        logger.error(f"Stop daemon error: {e}")


# ── clone ─────────────────────────────────────────────────────────────────────

def clone_from_main(remote_ip, safe_name, save_path):
    """
    Clone from main device using safe_name.
    Handles: empty folder, existing git repo, non-empty folder.
    """
    save_path = os.path.realpath(resolve_case_insensitive_path(_clean_path(save_path)))
    url = f"git://{remote_ip}/{safe_name}"
    logger.info(f"Cloning from {url} into {save_path}")
    os.makedirs(save_path, exist_ok=True)

    # Already a git repo → update remote and pull
    if is_git_repo(save_path):
        logger.info("Folder already has .git — updating remote")
        _run(["git", "remote", "remove", "origin"], cwd=save_path)
        _run(["git", "remote", "add", "origin", url], cwd=save_path)

        # Set user if not set
        ok, name = _run(["git", "config", "user.name"], cwd=save_path)
        if not ok or not name:
            _run(["git", "config", "user.name",  socket.gethostname()], cwd=save_path)
            _run(["git", "config", "user.email", "lab@sharing.local"],  cwd=save_path)

        ok, out = _run(["git", "fetch", "origin"], cwd=save_path)
        if ok:
            branch = get_current_branch(save_path)
            ok2, out2 = _run(
                ["git", "pull", "--rebase=false", "origin", branch], cwd=save_path)
            return ok2, out2
        return ok, out

    # Empty folder → clone directly
    if not os.listdir(save_path):
        ok, out = _run(["git", "clone", url, "."], cwd=save_path)
        if ok:
            _run(["git", "config", "user.name",  socket.gethostname()], cwd=save_path)
            _run(["git", "config", "user.email", "lab@sharing.local"],  cwd=save_path)
            logger.info("Clone successful ✅")
        return ok, out

    # Non-empty folder without .git — smart recovery:
    # init the folder, connect to server, fetch, reset to match server.
    # This means ANY existing folder is accepted as-is, no user action needed.
    logger.info(
        "Folder has files but no .git — initializing and connecting to server…"
    )
    _run(["git", "init"], cwd=save_path)
    _run(["git", "remote", "add", "origin", url], cwd=save_path)
    _run(["git", "config", "user.name",  socket.gethostname()], cwd=save_path)
    _run(["git", "config", "user.email", "lab@sharing.local"],  cwd=save_path)

    ok_fetch, fetch_out = _run(["git", "fetch", "origin"], cwd=save_path, timeout=30)
    if not ok_fetch:
        return False, f"Could not reach server at {url}: {fetch_out}"

    # Determine the branch from the remote
    ok_br, remote_branches = _run(
        ["git", "branch", "-r"], cwd=save_path, timeout=10)
    branch = "main"
    if ok_br and "origin/main" not in remote_branches and "origin/master" in remote_branches:
        branch = "master"

    # Reset working tree to server state (local files replaced by server version)
    ok_reset, reset_out = _run(
        ["git", "reset", "--hard", f"origin/{branch}"], cwd=save_path, timeout=30)
    if ok_reset:
        # Set the local branch to track the remote
        _run(["git", "checkout", "-B", branch, f"origin/{branch}"], cwd=save_path)
        logger.info(f"Folder initialized and synced to server @ {branch} ✅")
    return ok_reset, reset_out


# ── git operations ────────────────────────────────────────────────────────────

def commit(repo_path, message):
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    logger.info(f"Committing: {message}")
    _run(["git", "add", "."], cwd=repo_path)
    ok, out = _run(["git", "commit", "-m", message], cwd=repo_path)
    if not ok and ("nothing to commit" in out or "nothing added" in out):
        return False, "Nothing to commit — no changes detected"
    logger.info(f"Commit result: {out}")
    return ok, out


def commit_and_push(repo_path, message, remote_ip=None, safe_name=None):
    """
    Atomic Commit + Push for client devices.
    Yields (step_name, ok, output) for each stage so the caller
    can emit log signals with per-step progress.

    Steps:
      1. 'add'    — git add .
      2. 'commit' — git commit -m message
      3. 'push'   — git push origin <branch>   (only if remote available)
    """
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))

    # ── Step 1: git add ──────────────────────────────────────────
    ok, out = _run(["git", "add", "."], cwd=repo_path)
    yield "add", ok, out if out else "Staged all changes"

    if not ok:
        return  # abort pipeline on hard failure

    # ── Step 2: git commit ───────────────────────────────────────
    ok, out = _run(["git", "commit", "-m", message], cwd=repo_path)
    if not ok and ("nothing to commit" in out or "nothing added" in out):
        yield "commit", True, "Nothing to commit — working tree is clean"
    else:
        yield "commit", ok, out
        if not ok:
            return  # abort if commit failed

    # Capture commit hash for notification
    _, commit_hash = _run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=repo_path)

    # ── Step 3: push (client only) ───────────────────────────────
    if remote_ip and safe_name:
        fix_remote(repo_path, remote_ip, safe_name)

    ok_remote, remotes = _run(["git", "remote"], cwd=repo_path)
    has_remote = ok_remote and "origin" in remotes.split()

    if has_remote:
        ok2, branch = _run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
        branch = branch.strip() if (ok2 and branch.strip()) else "master"

        # Get the remote URL to check if it's a local bare repo (MAIN device)
        _, remote_url = _run(["git", "remote", "get-url", "origin"], cwd=repo_path)
        is_local_repo = remote_url.strip().startswith("/")  # local path = MAIN device

        # Push to remote (works for both client→remote and main→local bare repo)
        ok3, out3 = _run(["git", "push", "origin", branch], cwd=repo_path)

        yield "push", ok3, out3
        if ok3:
            yield "hash", True, commit_hash   # caller uses this to build notification
    else:
        # No remote configured at all — just signal success with commit hash
        yield "push", True, "No remote configured — commit saved locally only"
        yield "hash", True, commit_hash




def push(repo_path):
    """Push to origin — works for both main (push to itself) and client"""
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    logger.info("Pushing...")

    # Get current branch
    ok, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    if not ok or not branch:
        branch = "main"

    ok, out = _run(["git", "push", "origin", branch], cwd=repo_path)
    logger.info(f"Push result: {out}")
    return ok, out


def pull(repo_path, role="client", config=None):
    """Pull changes from origin into the working tree."""
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    logger.info("Pulling...")

    ok_remote, remotes = _run(["git", "remote"], cwd=repo_path)
    if not ok_remote:
        return False, remotes

    branch = get_configured_branch(config, repo_path)

    # Fetch first
    ok, out = _run(["git", "fetch", "origin"], cwd=repo_path, timeout=30)
    if not ok:
        logger.error(f"Fetch failed: {out}")
        return ok, out

    # Check if there are incoming changes
    ok2, diff = _run(
        ["git", "log", f"HEAD..origin/{branch}", "--oneline"],
        cwd=repo_path, timeout=10)

    if ok2 and diff.strip():
        # There are new commits — try merge first
        ok3, out3 = _run(
            ["git", "merge", f"origin/{branch}", "--no-edit"],
            cwd=repo_path, timeout=30)

        if ok3:
            logger.info(f"Merged origin/{branch} — working tree updated ✅")
            return ok3, out3

        # ── Merge blocked by untracked files? ────────────────────────────
        # Git refuses to overwrite untracked files during merge.
        # Strategy: back them up to a timestamped folder, then reset --hard.
        # The user's local-only files are preserved — nothing is deleted.
        if "untracked working tree files would be overwritten" in out3.lower():
            logger.warning(
                "[pull] Merge blocked by untracked files — backing up and retrying…"
            )
            # Extract the conflicting file paths from the error message
            conflicting = []
            capture = False
            for line in out3.splitlines():
                if "untracked working tree files" in line.lower():
                    capture = True
                    continue
                if capture:
                    stripped = line.strip()
                    if stripped and not stripped.lower().startswith("please"):
                        conflicting.append(stripped)
                    else:
                        capture = False

            # Back up each conflicting file
            if conflicting:
                import datetime
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_dir = os.path.join(repo_path, f"_lab_untracked_backup_{ts}")
                os.makedirs(backup_dir, exist_ok=True)
                for rel_path in conflicting:
                    src = os.path.join(repo_path, rel_path)
                    dst = os.path.join(backup_dir, rel_path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    try:
                        shutil.move(src, dst)
                        logger.info(f"[pull] Backed up: {rel_path} → {backup_dir}")
                    except Exception as e:
                        logger.warning(f"[pull] Could not back up {rel_path}: {e}")

            # Now reset --hard to server state (untracked files are gone/backed up)
            ok4, out4 = _run(
                ["git", "reset", "--hard", f"origin/{branch}"],
                cwd=repo_path, timeout=30)
            if ok4:
                note = (
                    f"Pulled (reset) — {len(conflicting)} local untracked file(s) "
                    f"backed up to: {os.path.basename(backup_dir)}"
                    if conflicting else f"Pulled (reset) to origin/{branch}"
                )
                logger.info(f"[pull] {note} ✅")
                return True, note
            return False, f"Reset after backup failed: {out4}"

        # Some other merge failure (e.g. real conflict in tracked files)
        logger.warning(f"Merge had issues: {out3}")
        return ok3, out3

    else:
        logger.info("Already up to date.")
        return True, "Already up to date."


def auto_pull(repo_path):
    """Silent pull for auto-sync, only logs if there is a change"""
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    # Get current branch
    ok, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    if not ok or not branch:
        branch = "main"

    ok, out = _run(["git", "fetch", "origin"], cwd=repo_path, timeout=30, silent=True)
    if not ok:
        return False, f"Auto-fetch failed: {out}"

    ok2, diff = _run(["git", "log", f"HEAD..origin/{branch}", "--oneline"], cwd=repo_path, timeout=10)
    if ok2 and diff.strip():
        logger.info("Auto-sync: new changes detected, pulling...")
        ok3, out3 = _run(["git", "reset", "--hard", f"origin/{branch}"], cwd=repo_path, timeout=30)
        if ok3:
            return True, f"Auto-sync updated working tree:\n{out3}"
        ok3, out3 = _run(["git", "pull", "--rebase=false", "origin", branch], cwd=repo_path, timeout=30)
        return ok3, f"Auto-sync pulled:\n{out3}"
    
    return True, ""  # empty string means nothing to do

def get_diff(repo_path):
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    ok, out = _run(["git", "diff", "HEAD", "--stat"], cwd=repo_path, timeout=10)
    if not out:
        ok, out = _run(["git", "diff", "--stat"], cwd=repo_path, timeout=10)
    return out if out else "No changes"


def get_history(repo_path, limit=20):
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    ok, out = _run(
        ["git", "log", f"--max-count={limit}",
         "--pretty=format:%H|%s|%an|%ar"],
        cwd=repo_path
    )
    if not ok or not out:
        return []
    entries = []
    for line in out.strip().split("\n"):
        if "|" not in line:
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            entries.append({
                "hash":      parts[0][:8],
                "full_hash": parts[0],
                "message":   parts[1],
                "author":    parts[2],
                "time":      parts[3],
            })
    return entries


def revert_to(repo_path, commit_hash):
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    logger.info(f"Reverting to {commit_hash}")
    ok, out = _run(["git", "read-tree", "-um", "HEAD", commit_hash], cwd=repo_path)
    if ok:
        _run(["git", "add", "."], cwd=repo_path)
        ok2, out2 = _run(
            ["git", "commit", "-m", f"Revert to {commit_hash} via Lab Sharing"],
            cwd=repo_path)
        return ok2, out2
    return ok, out


def get_status(repo_path):
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    ok, out = _run(["git", "status", "--short"], cwd=repo_path, timeout=10)
    return out if out else "Clean — no changes"


def fix_remote(repo_path, remote_ip, safe_name):
    """Fix remote URL — called automatically on pull/push if needed"""
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    url = f"git://{remote_ip}/{safe_name}"
    _run(["git", "remote", "remove", "origin"], cwd=repo_path)
    _run(["git", "remote", "add", "origin", url], cwd=repo_path)
    logger.info(f"Remote fixed: {url}")
    return url

def get_conflicts(repo_path):
    """Return a list of unmerged files (conflicts)"""
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    ok, out = _run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=repo_path)
    if ok and out:
        return out.splitlines()
    return []

def resolve_conflict(repo_path, strategy="ours"):
    """Resolve conflicts keeping 'ours' or 'theirs'"""
    repo_path = os.path.realpath(resolve_case_insensitive_path(repo_path))
    
    # Get unmerged files
    conflicts = get_conflicts(repo_path)
    if not conflicts:
        return False, "No conflicts found."
        
    for f in conflicts:
        if strategy == "ours":
            _run(["git", "checkout", "--ours", "--", f], cwd=repo_path)
        else:
            _run(["git", "checkout", "--theirs", "--", f], cwd=repo_path)
        _run(["git", "add", f], cwd=repo_path)
        
    ok, out = _run(["git", "commit", "-m", f"Resolved merge conflicts using {strategy} changes"], cwd=repo_path)
    return ok, out
