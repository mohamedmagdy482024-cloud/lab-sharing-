import os
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QStackedWidget, QMessageBox, QFileDialog, QSizePolicy, QFrame,
    QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from core import git_manager as gm
from core.logger import logger
from core.change_watcher import ChangeWatcher
from core import sync_state
from gui.notification_banner import BannerStack, NotificationBanner, STYLE_WARN, STYLE_REMOTE, STYLE_ERROR
from core.messaging import send_message
from core.platform import notify_user
import socket

STYLE_INPUT = """
    QLineEdit {
        background-color: #313244;
        color: #cdd6f4;
        border: 1px solid #585b70;
        border-radius: 6px;
        padding: 7px 10px;
        font-size: 12px;
    }
    QLineEdit:focus { border-color: #89b4fa; }
"""


def _lbl(text, color="#cdd6f4", size=12, bold=False):
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{color};font-size:{size}px;"
        f"font-weight:{'bold' if bold else 'normal'};background:transparent;"
    )
    l.setWordWrap(True)
    return l


def _btn(text, bg, fg="#1e1e2e"):
    b = QPushButton(text)
    b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    b.setStyleSheet(f"""
        QPushButton {{
            background-color:{bg}; color:{fg};
            border:none; border-radius:6px;
            padding:8px 14px; font-size:12px; font-weight:bold;
        }}
        QPushButton:hover {{ background-color:{bg}cc; }}
        QPushButton:disabled {{ background-color:#313244; color:#6c7086; }}
    """)
    return b


def _card():
    f = QFrame()
    f.setStyleSheet(
        "QFrame{background-color:#181825;"
        "border-radius:8px;border:1px solid #313244;}"
    )
    return f


def _div():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color:#313244;")
    f.setFixedHeight(1)
    return f



class SmartStack(QStackedWidget):
    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w else super().minimumSizeHint()

    def setCurrentIndex(self, idx):
        super().setCurrentIndex(idx)
        self.updateGeometry()

class GitSignals(QObject):

    log       = pyqtSignal(str, str)
    done      = pyqtSignal(bool, str)
    show_main = pyqtSignal()
    popup     = pyqtSignal(bool, str)   # success, message
    banner    = pyqtSignal(str, str, str, str)  # type, msg, action, icon
    conflict  = pyqtSignal()
    local_files = pyqtSignal(int)
    local_changes = pyqtSignal(list)
    peer_sync = pyqtSignal(str, str, str)  # ip, hostname, hash


class GitPanel(QWidget):
    def __init__(self, device_panel, log_panel=None):
        super().__init__()
        self.device_panel = device_panel
        self.log_panel    = log_panel
        self.signals      = GitSignals()
        self.config       = gm.load_config()

        self._build_ui()
        self._wire()

        if self.config:
            self._go_main()
        else:
            self._go_setup()

    # ── log helper ────────────────────────────────────────────────────────────
    def _log(self, msg, color="#a6adc8"):
        logger.info(msg)
        if self.log_panel:
            self.log_panel.append(msg, color)

    # ── build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.stack = SmartStack()
        root.addWidget(self.stack)
        self._build_setup()   # index 0
        self._build_main()    # index 1

    # ── Setup page ────────────────────────────────────────────────────────────
    def _build_setup(self):
        page = QWidget()
        page.setStyleSheet("background-color:#1e1e2e;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(16)

        outer.addWidget(_lbl("🔀  Git Sync — Device Setup", "#89b4fa", 15, True))
        outer.addWidget(_lbl("Choose the role of this device:", "#6c7086", 12))

        # ── MAIN card ──
        mc = _card()
        ml = QVBoxLayout(mc)
        ml.setContentsMargins(16, 14, 16, 14)
        ml.setSpacing(10)
        ml.addWidget(_lbl("🖥️   This is the MAIN device", "#a6e3a1", 13, True))
        ml.addWidget(_lbl(
            "I own the project. Other devices will sync from me.", "#a6adc8", 12))

        # Server Repo path
        ml.addWidget(_lbl("🗂️  Server repo folder (bare repo served to clients):", "#a6adc8", 11))
        ml.addWidget(_lbl(
            "→ Must be an EMPTY or new folder — not your editable project.\n"
            "  Example: C:/Users/you/lab_server/UI_sampel-main",
            "#585b70", 10))
        sr_m = QHBoxLayout(); sr_m.setSpacing(8)
        self.main_server_repo = QLineEdit()
        self.main_server_repo.setPlaceholderText(
            "C:/Users/you/lab_server/UI_sampel-main  (empty folder, bare repo)")
        self.main_server_repo.setStyleSheet(STYLE_INPUT)
        bsr_m = _btn("📂", "#313244", "#cdd6f4"); bsr_m.setFixedWidth(36)
        bsr_m.clicked.connect(lambda: self._browse(self.main_server_repo))
        sr_m.addWidget(self.main_server_repo); sr_m.addWidget(bsr_m)
        ml.addLayout(sr_m)

        ml.addWidget(_lbl("→ This is your working folder (client):", "#585b70", 11))

        pr = QHBoxLayout(); pr.setSpacing(8)
        self.main_path = QLineEdit()
        self.main_path.setPlaceholderText("Select your working folder…")
        self.main_path.setStyleSheet(STYLE_INPUT)
        bm = _btn("📂", "#313244", "#cdd6f4"); bm.setFixedWidth(36)
        bm.clicked.connect(lambda: self._browse(self.main_path))
        pr.addWidget(self.main_path); pr.addWidget(bm)
        ml.addLayout(pr)

        b = _btn("✅  Set as Main Device", "#a6e3a1")
        b.clicked.connect(self._setup_main)
        ml.addWidget(b, alignment=Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(mc)

        # ── CLIENT card ──
        cc = _card()
        cl = QVBoxLayout(cc)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)
        cl.addWidget(_lbl("💻   This is a CLIENT device", "#89b4fa", 13, True))
        cl.addWidget(_lbl(
            "I'll pull/push from the main device over LAN.", "#a6adc8", 12))

        # Main IP
        ir = QHBoxLayout(); ir.setSpacing(8)
        ir.addWidget(_lbl("Main IP:", "#a6adc8", 12))
        self.client_ip = QLineEdit()
        self.client_ip.setPlaceholderText("192.168.0.166")
        self.client_ip.setStyleSheet(STYLE_INPUT)
        ir.addWidget(self.client_ip)
        cl.addLayout(ir)

        # Repo name (safe_name from Main)
        rr = QHBoxLayout(); rr.setSpacing(8)
        rr.addWidget(_lbl("Repo name:", "#a6adc8", 12))
        self.client_repo_name = QLineEdit()
        self.client_repo_name.setPlaceholderText("my_project")
        self.client_repo_name.setStyleSheet(STYLE_INPUT)
        
        br_c = _btn("📂", "#313244", "#cdd6f4"); br_c.setFixedWidth(36)
        def _browse_repo_client():
            p = QFileDialog.getExistingDirectory(self, "Select Repo Folder", os.path.expanduser("~"))
            if p:
                self.client_repo_name.setText(os.path.basename(p))
        br_c.clicked.connect(_browse_repo_client)
        
        rr.addWidget(self.client_repo_name)
        rr.addWidget(br_c)
        cl.addLayout(rr)
        cl.addWidget(_lbl(
            "→ On Main: check Live Log for 'Clients connect to: git://...'\n  and copy the repo name (last part of the URL)", "#6c7086", 10))

        # Local save path
        sr = QHBoxLayout(); sr.setSpacing(8)
        self.client_path = QLineEdit()
        self.client_path.setPlaceholderText("Local folder to save the project…")
        self.client_path.setStyleSheet(STYLE_INPUT)
        bc = _btn("📂", "#313244", "#cdd6f4"); bc.setFixedWidth(36)
        bc.clicked.connect(lambda: self._browse(self.client_path))
        sr.addWidget(self.client_path); sr.addWidget(bc)
        cl.addLayout(sr)

        b2 = _btn("🔗  Connect to Main Device", "#89b4fa")
        b2.clicked.connect(self._setup_client)
        cl.addWidget(b2, alignment=Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(cc)
        outer.addStretch()
        self.stack.addWidget(page)  # index 0

    # ── Main git page ──────────────────────────────────────────────────────────
    def _build_main(self):
        page = QWidget()
        page.setStyleSheet("background-color:#1e1e2e;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        self.banner_stack = BannerStack(page)
        outer.addWidget(self.banner_stack)

        # Role + repo info
        top = QHBoxLayout()
        self.role_lbl = _lbl("", "#89b4fa", 12, True)
        top.addWidget(self.role_lbl)
        top.addStretch()
        rst = _btn("⚙ Reset", "#313244", "#a6adc8")
        rst.clicked.connect(self._reset)
        top.addWidget(rst)
        outer.addLayout(top)

        self.repo_lbl = _lbl("", "#6c7086", 11)
        outer.addWidget(self.repo_lbl)

        self.hint_lbl = _lbl(
            "Edit files in the working folder above — not the bare server folder.",
            "#585b70", 10)
        outer.addWidget(self.hint_lbl)

        self.sync_status_lbl = _lbl("", "#a6adc8", 10)
        outer.addWidget(self.sync_status_lbl)

        # Auto-pull when remote notifies (client / main receiving client push)
        ap_row = QHBoxLayout()
        ap_row.addWidget(_lbl("Auto-pull on remote update:", "#6c7086", 11))
        self.auto_pull_combo = QComboBox()
        self.auto_pull_combo.addItems(["Off", "On"])
        self.auto_pull_combo.setStyleSheet(
            "QComboBox{background:#313244;color:#cdd6f4;border:1px solid #585b70;"
            "border-radius:6px;padding:4px 8px;}")
        self.auto_pull_combo.currentTextChanged.connect(self._on_auto_pull_changed)
        ap_row.addWidget(self.auto_pull_combo)
        ap_row.addStretch()
        outer.addLayout(ap_row)

        outer.addWidget(_div())

        # Action buttons — Send / Receive (Commit & Push / Pull)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        self.commit_push_btn = _btn("📤  Send", "#f9e2af")
        self.commit_push_btn.setToolTip("Commit local changes and push to Main Server Repo")
        self.commit_push_btn.clicked.connect(self._do_commit_push)
        btn_row.addWidget(self.commit_push_btn)

        self.pull_btn = _btn("📥  Receive", "#a6e3a1")
        self.pull_btn.setToolTip("Pull latest changes from Main Server Repo into working folder")
        self.pull_btn.clicked.connect(self._do_pull)
        btn_row.addWidget(self.pull_btn)

        self.revert_btn = _btn("↩ Revert", "#f38ba8")
        self.revert_btn.clicked.connect(self._do_revert)
        btn_row.addWidget(self.revert_btn)

        change_btn = _btn("📂 Change Repo", "#cba6f7")
        change_btn.clicked.connect(self._change_repo)
        btn_row.addWidget(change_btn)

        btn_row.addStretch()
        outer.addLayout(btn_row)

        # Commit message
        self.commit_msg = QLineEdit()
        self.commit_msg.setPlaceholderText(
            "Commit message — describe what changed…  "
            "(also paste commit ID here for Revert)")
        self.commit_msg.setStyleSheet(STYLE_INPUT)
        outer.addWidget(self.commit_msg)

        outer.addStretch()
        self.stack.addWidget(page)  # index 1

    # ── wire signals ──────────────────────────────────────────────────────────
    def _wire(self):
        self.signals.log.connect(lambda m, c: self._log(m, c))
        self.signals.done.connect(self._on_done)
        self.signals.show_main.connect(self._go_main)
        self.signals.popup.connect(self._show_popup)
        self.signals.banner.connect(self._show_banner)
        self.signals.conflict.connect(self._handle_conflict)
        self.signals.local_files.connect(self._update_change_badge)
        self.signals.local_changes.connect(self._handle_local_changes)
        self.signals.peer_sync.connect(self._on_peer_sync)

    def _on_auto_pull_changed(self, text):
        if not self.config:
            return
        mode = "on" if text == "On" else "off"
        gm.save_config(
            self.config["role"],
            self.config["repo_path"],
            remote_ip=self.config.get("remote_ip"),
            safe_name=self.config.get("safe_name"),
            server_repo_path=self.config.get("server_repo_path"),
            default_branch=self.config.get("default_branch"),
            auto_pull=mode,
        )
        self.config = gm.load_config()

    def _refresh_sync_status(self, server_head=None):
        if not self.config or self.config.get("role") != "main":
            self.sync_status_lbl.setText("")
            return
        line = sync_state.format_sync_status_line(server_head)
        self.sync_status_lbl.setText(line)

    def _on_peer_sync(self, peer_ip, hostname, commit_hash):
        if peer_ip:
            self._log(
                f"✅ Client synced: {hostname} ({peer_ip}) @ {commit_hash}",
                "#a6e3a1",
            )
        self._refresh_sync_status(commit_hash or None)

    # ── browse helper ─────────────────────────────────────────────────────────
    def _browse(self, line_edit):
        p = QFileDialog.getExistingDirectory(
            self, "Select Folder", os.path.expanduser("~"))
        if p:
            line_edit.setText(p)

    # ── Setup: Main ──────────────────────────────────────────────────────────
    def _setup_main(self):
        # Always strip all leading/trailing whitespace
        repo = self.main_path.text().strip()
        server_repo = self.main_server_repo.text().strip()
        if not repo:
            QMessageBox.warning(self, "Missing", "Please select the working folder.")
            return
        if not server_repo:
            QMessageBox.warning(self, "Missing", "Please select the server repo folder.")
            return

        self._log("=== GIT SETUP: MAIN ===", "#89b4fa")
        ok, msg = gm.init_main_repo(repo, server_repo_path=server_repo)
        if not ok:
            self.signals.log.emit(f"❌ {msg}", "#f38ba8")
            QMessageBox.critical(self, "Setup failed", msg)
            return
        self._log(f"✅ {msg}", "#a6e3a1")

        def _start():
            proc, port, safe_name = gm.start_git_daemon(repo, server_repo_path=server_repo)
            if port:
                # Resolve local IP so user knows exactly what URL clients should use
                try:
                    import socket as _socket
                    s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    s.close()
                except Exception:
                    local_ip = "?.?.?.?"

                self.signals.log.emit(
                    f"✅ Git daemon ready", "#a6e3a1")
                self.signals.log.emit(
                    f"📁 Repo name: {safe_name}", "#f9e2af")
                self.signals.log.emit(
                    f"🌐 Clients connect to: git://{local_ip}/{safe_name}", "#89b4fa")
                self.signals.log.emit(
                    f"🗄️  Bare server repo: {os.path.realpath(server_repo)}", "#6c7086")
                self.signals.log.emit(
                    f"📂 Working copy: {os.path.realpath(repo)}", "#6c7086")
            else:
                self.signals.log.emit(
                    "❌ Git daemon failed to start", "#f38ba8")
            gm.save_config("main", repo, safe_name=safe_name, server_repo_path=server_repo,
                           default_branch=gm.get_current_branch(repo))
            self.config = gm.load_config()
            self.signals.show_main.emit()

        threading.Thread(target=_start, daemon=True).start()

    # ── Setup: Client ────────────────────────────────────────────────────────
    def _setup_client(self):
        ip        = self.client_ip.text().strip()
        path      = self.client_path.text().strip()
        repo_name = self.client_repo_name.text().strip()

        if not ip:
            QMessageBox.warning(self, "Missing", "Please enter Main device IP.")
            return
        if not repo_name:
            QMessageBox.warning(self, "Missing",
                "Please enter Repo name (check Live Log on Main device).")
            return
        if not path:
            QMessageBox.warning(self, "Missing", "Please select a local folder.")
            return

        self._log(f"=== GIT SETUP: CLIENT → {ip} ===", "#89b4fa")
        self._log(f"Cloning repo: {repo_name}", "#a6adc8")

        def _clone():
            ok, msg = gm.clone_from_main(ip, repo_name, path)
            if ok:
                gm.save_config("client", path, remote_ip=ip, safe_name=repo_name,
                               default_branch=gm.get_current_branch(path))
                self.config = gm.load_config()
                self.signals.log.emit("✅ Clone successful! Repo is ready.", "#a6e3a1")
                self.signals.show_main.emit()
            else:
                self.signals.log.emit(f"❌ {msg}", "#f38ba8")
                self.signals.done.emit(False, msg)

        threading.Thread(target=_clone, daemon=True).start()

    # ── navigation ────────────────────────────────────────────────────────────
    def _go_setup(self):
        self.stack.setCurrentIndex(0)

    def _go_main(self):
        if not self.config:
            return
        role      = self.config.get("role", "")
        repo      = self.config.get("repo_path", "")
        safe_name = self.config.get("safe_name", "")

        self.role_lbl.setText(
            "🖥️  MAIN (Server)" if role == "main" else "💻  CLIENT")
        self.repo_lbl.setText(f"Working folder: {repo}")

        bare = gm.get_bare_repo_path(self.config) if role == "main" else None
        if bare and repo:
            repo_norm = os.path.normcase(os.path.normpath(repo))
            bare_norm = os.path.normcase(os.path.normpath(bare))
            if repo_norm == bare_norm or repo_norm.startswith(bare_norm + os.sep):
                self._log(
                    "⚠️ Working folder equals server bare folder — "
                    "pick a separate working copy (e.g. … - Copy)",
                    "#f9e2af",
                )
        self._last_local_count = 0

        self.commit_push_btn.setText("📤  Send")

        ap = (self.config.get("auto_pull") or "off").lower()
        self.auto_pull_combo.blockSignals(True)
        self.auto_pull_combo.setCurrentText("On" if ap == "on" else "Off")
        self.auto_pull_combo.blockSignals(False)

        mirror = gm.get_server_mirror_path(self.config) if role == "main" else None
        if mirror:
            self.hint_lbl.setText(
                f"Edit working folder only · Browse server files: {mirror}")
        else:
            self.hint_lbl.setText(
                "Edit files in the working folder — not the bare server folder.")

        self._refresh_sync_status()

        self.stack.setCurrentIndex(1)

        # Repair non-bare server immediately (must run before push)
        if role == "main":
            bare = gm.get_bare_repo_path(self.config)
            if bare and not gm.is_bare_repo(bare):
                self._log("🔧 Server folder is not bare — repairing now…", "#f9e2af")
                ok_r, msg_r = gm.repair_server_bare_if_needed(self.config)
                if ok_r:
                    self._log(f"✅ {msg_r}", "#a6e3a1")
                    gm.stop_git_daemon()
                else:
                    self._log(f"❌ Repair failed: {msg_r}", "#f38ba8")
                    QMessageBox.critical(
                        self, "Server repair failed",
                        str(msg_r) + "\n\nClose OneDrive sync or pick a new server folder.")

        # Auto-check daemon for main
        if role == "main":
            def _check():
                # Re-read config inside the thread so heal_config_paths has
                # already run and all paths are guaranteed to be clean.
                cfg_live = gm.load_config() or {}
                server_repo_live = cfg_live.get("server_repo_path")
                daemon_kw = {"server_repo_path": server_repo_live} if server_repo_live else {}

                if gm.is_daemon_running():
                    self.signals.log.emit(
                        f"✅ Git daemon running — repo name: {cfg_live.get('safe_name', safe_name)}",
                        "#a6e3a1")
                else:
                    self.signals.log.emit("🔄 Starting git daemon…", "#f9e2af")
                    proc, port, sn = gm.start_git_daemon(repo, **daemon_kw)
                    if port:
                        self.signals.log.emit(
                            f"✅ Git daemon started — repo name: {sn}", "#a6e3a1")
                    else:
                        self.signals.log.emit(
                            "❌ Git daemon failed — check if port 9418 is free",
                            "#f38ba8")

                bare = gm.get_bare_repo_path(cfg_live)
                if bare:
                    self.signals.log.emit(f"🗄️  Bare server repo: {bare}", "#6c7086")
                    if gm.is_bare_repo(bare):
                        self.signals.log.emit("✅ Server repo is bare (ready for push)", "#a6e3a1")
                    else:
                        self.signals.log.emit(
                            "⚠️ Server repo is still not bare — push will fail",
                            "#f38ba8",
                        )
            threading.Thread(target=_check, daemon=True).start()


        self._show_status()
        
        self._start_smart_sync()

    def _start_smart_sync(self):
        if not self.config:
            return
        repo = self.config.get("repo_path", "")
        role = self.config.get("role", "")

        # 1. Local changes watcher — restart if path changed or not yet started
        current_watcher_path = getattr(self, "_watcher_repo_path", None)
        if current_watcher_path != repo:
            # Stop old watcher if running
            if hasattr(self, "change_watcher"):
                try:
                    self.change_watcher.stop()
                except Exception:
                    pass
            self._watcher_repo_path = repo
            self.change_watcher = ChangeWatcher(
                repo_path=repo,
                on_change=self._on_local_changes,
                is_busy=lambda: getattr(self, "_is_syncing", False)
            )
            self.change_watcher.start()
            logger.info(f"ChangeWatcher (re)started for: {repo}")
            self.signals.log.emit(
                f"👁️ Watching for edits in: {repo}", "#6c7086")

        # 2. Remote changes fetch timer
        if not hasattr(self, "fetch_timer"):
            from PyQt6.QtCore import QTimer
            self.fetch_timer = QTimer(self)
            self.fetch_timer.timeout.connect(self._do_fetch_check)
            self.fetch_timer.start(30_000)

    def _update_change_badge(self, n):
        if n > 0:
            self.commit_push_btn.setText(f"📤  Send ({n})")
        elif hasattr(self, "commit_push_btn"):
            self.commit_push_btn.setText("📤  Send")

    def _on_local_changes(self, changed_files):
        """Called from ChangeWatcher thread — queue handling on the GUI thread."""
        self.signals.local_changes.emit(changed_files)

    def _parse_changed_paths(self, status_lines):
        """Extract file paths from git status --short lines."""
        paths = []
        for line in status_lines:
            line = line.rstrip()
            if not line:
                continue
            if " -> " in line:
                paths.append(line.split(" -> ", 1)[1].strip())
            elif len(line) > 3:
                paths.append(line[3:].strip())
            else:
                paths.append(line.strip())
        return paths

    def _handle_local_changes(self, changed_files):
        """Main thread: show banner when git detects uncommitted changes."""
        n = len(changed_files)
        if n == getattr(self, "_last_local_count", -1):
            return
        self._last_local_count = n
        if n == 0:
            self.signals.local_files.emit(0)
            return
        paths = self._parse_changed_paths(changed_files)
        shown = paths[:4]
        label = ", ".join(os.path.basename(p) for p in shown)
        if len(paths) > 4:
            label += f" (+{len(paths) - 4} more)"
        detail = f"Modified: {label} — not on server yet."
        self.signals.banner.emit("local", detail, "Send", "💡")
        self.signals.local_files.emit(n)
        self._log(f"Modified ({n}):", "#f9e2af")
        for p in paths[:12]:
            self._log(f"  • {p}", "#a6adc8")
        if len(paths) > 12:
            self._log(f"  … and {len(paths) - 12} more", "#6c7086")
        notify_user(
            "Lab Sharing",
            f"{n} file(s) modified — open Git Sync and press Send",
        )

    def _do_fetch_check(self):
        if not self.config:
            return
        if getattr(self, "_is_syncing", False) or getattr(self, "_is_fetching", False):
            return
        repo = self.config.get("repo_path", "")
        role = self.config.get("role", "")
        remote_ip = self.config.get("remote_ip", "")
        safe_name = self.config.get("safe_name", "")

        def _r():
            self._is_fetching = True
            try:
                import subprocess
                if not repo or not os.path.isdir(repo):
                    return
                res_remote = subprocess.run(
                    ["git", "remote"], cwd=repo, capture_output=True, text=True, timeout=5)
                if "origin" not in res_remote.stdout.split():
                    return

                branch = gm.get_configured_branch(self.config, repo)

                res_fetch = subprocess.run(
                    ["git", "fetch", "origin"],
                    cwd=repo, capture_output=True, text=True, timeout=15)
                if res_fetch.returncode != 0:
                    err = (res_fetch.stderr or res_fetch.stdout or "fetch failed").strip()
                    short = err.splitlines()[0][:100] if err else "Cannot reach server"
                    self.signals.log.emit(f"⚠️ Fetch failed: {short}", "#f38ba8")
                    self.signals.banner.emit(
                        "error",
                        f"Cannot reach server — {short}",
                        "Retry Pull",
                        "⚠️",
                    )
                    return

                res = subprocess.run(
                    ["git", "log", f"HEAD..origin/{branch}", "--oneline"],
                    cwd=repo, capture_output=True, text=True, timeout=5)
                lines = [l for l in res.stdout.strip().splitlines() if l.strip()]
                if lines:
                    self.signals.banner.emit(
                        "remote", f"Remote has {len(lines)} new commits.", "Receive", "📥")
                    cfg = gm.load_config()
                    if cfg and (cfg.get("auto_pull") or "off").lower() == "on":
                        self._do_pull(auto=True)
            except subprocess.TimeoutExpired:
                self.signals.log.emit("⚠️ Fetch timed out — is Main running?", "#f38ba8")
                self.signals.banner.emit(
                    "error", "Cannot reach server — fetch timed out", "Retry Pull", "⚠️")
            except Exception as e:
                self.signals.log.emit(f"⚠️ Fetch check error: {e}", "#f38ba8")
            finally:
                self._is_fetching = False

        threading.Thread(target=_r, daemon=True).start()

    def _show_banner(self, btype, msg, action, icon):
        try:
            for b in list(self.banner_stack._banners):
                if b._msg_lbl.text() == msg:
                    return
                    
            style = STYLE_WARN if btype == "local" else STYLE_ERROR if btype == "error" else STYLE_REMOTE
            b = NotificationBanner(msg, action_label=action, icon=icon, style=style, parent=self.stack.widget(1))
            if btype == "local":
                b.action_clicked.connect(lambda: self.commit_msg.setFocus())
            else:
                b.action_clicked.connect(self._do_pull)
            self.banner_stack.push(b)
        except Exception as e:
            logger.error(f"Banner display error: {e}")

    def _reset(self):
        r = QMessageBox.question(
            self, "Reset Git Setup",
            "This will remove the Git config.\n"
            "Your repo files will NOT be deleted.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            if os.path.exists(gm.GIT_CONFIG_FILE):
                os.remove(gm.GIT_CONFIG_FILE)
            # Stop daemon only if user explicitly resets
            gm.stop_git_daemon()
            self.config = None
            self._go_setup()

    # ── Change repo ───────────────────────────────────────────────────────────
    def _change_repo(self):
        p = QFileDialog.getExistingDirectory(
            self, "Select Project Folder", os.path.expanduser("~"))
        if not p:
            return
        role = self.config.get("role", "main") if self.config else "main"
        server_repo = (self.config.get("server_repo_path") if self.config else None)
        remote_ip = self.config.get("remote_ip") if self.config else None
        safe_name_cfg = self.config.get("safe_name") if self.config else None
        self._log(f"📂 Changing repo to: {p}", "#cba6f7")

        def _switch():
            if role == "main":
                if not server_repo:
                    self.signals.log.emit(
                        "❌ No server repo path in config — use Reset and set up Main again",
                        "#f38ba8")
                    return
                ok, msg = gm.init_main_repo(p, server_repo_path=server_repo)
                if ok:
                    proc, port, safe_name = gm.start_git_daemon(
                        p, server_repo_path=server_repo)
                    gm.save_config(
                        role, p,
                        remote_ip=remote_ip,
                        safe_name=safe_name or safe_name_cfg,
                        server_repo_path=server_repo,
                    )
                    self.config = gm.load_config()
                    self.signals.log.emit(f"✅ Switched to: {p}", "#a6e3a1")
                    self.signals.show_main.emit()
                else:
                    self.signals.log.emit(f"❌ {msg}", "#f38ba8")
            else:
                if not gm.is_git_repo(p):
                    self.signals.log.emit(
                        "❌ Selected folder is not a git repo — clone or init first",
                        "#f38ba8")
                    return
                gm.save_config(
                    "client", p,
                    remote_ip=remote_ip,
                    safe_name=safe_name_cfg,
                )
                self.config = gm.load_config()
                self.signals.log.emit(f"✅ Switched client working folder to: {p}", "#a6e3a1")
                self.signals.show_main.emit()

        threading.Thread(target=_switch, daemon=True).start()

    # ── Git actions ───────────────────────────────────────────────────────────
    def _do_commit_push(self):
        if getattr(self, "_is_syncing", False):
            QMessageBox.information(
                self, "Busy", "A sync is already in progress. Please wait.")
            return
        msg = self.commit_msg.text().strip()
        if not msg:
            QMessageBox.warning(self, "No Message", "Enter a commit message first.")
            return
        repo = self.config.get("repo_path", "")
        role = self.config.get("role", "")
        remote_ip = self.config.get("remote_ip", "")
        safe_name = self.config.get("safe_name", "")
        bare_path = gm.get_bare_repo_path(self.config) if role == "main" else None

        self.commit_push_btn.setEnabled(False)
        self.commit_push_btn.setText("⏳ Processing…")
        self._is_syncing = True
        self._log(f"── 💾 Committing: '{msg}' ──", "#f9e2af")

        def _r():
            final_message = "Commit & Push complete"
            try:
                commit_hash = None
                success = True
                pushed = False
                for step, ok, out in gm.commit_and_push(repo, msg, remote_ip if role == "client" else None, safe_name):
                    if step == "hash":
                        commit_hash = out
                        continue
                    self.signals.log.emit(out, "#a6e3a1" if ok else "#f38ba8")
                    if step == "push" and ok:
                        pushed = True
                    if not ok:
                        push_hint = gm.explain_push_error(out) if step == "push" else None
                        if push_hint and role == "main":
                            self.signals.log.emit(
                                "🔧 Attempting to repair server repo…", "#f9e2af")
                            ok_r, msg_r = gm.repair_server_bare_if_needed(self.config)
                            self.signals.log.emit(
                                msg_r, "#a6e3a1" if ok_r else "#f38ba8")
                            if ok_r:
                                server_rp = self.config.get("server_repo_path")
                                kw = {"server_repo_path": server_rp} if server_rp else {}
                                gm.stop_git_daemon()
                                gm.start_git_daemon(repo, **kw)
                                ok_push, out_push = gm.push(repo)
                                if ok_push:
                                    self.signals.log.emit(out_push, "#a6e3a1")
                                    pushed = True
                                    continue
                                out = out_push
                                push_hint = gm.explain_push_error(out_push)
                        if push_hint:
                            self.signals.log.emit(push_hint, "#f38ba8")
                            final_message = push_hint
                            success = False
                            break
                        if step == "push" and (
                            "fetch first" in out.lower()
                            or "non-fast-forward" in out.lower()
                            or ("rejected" in out.lower() and "checked out" not in out.lower())
                        ):
                            self.signals.log.emit("Remote has new changes. Merging first...", "#f9e2af")
                            ok_pull, out_pull = gm.pull(repo, role=role, config=self.config)
                            if not ok_pull and gm.get_conflicts(repo):
                                self.signals.conflict.emit()
                                success = False
                                break
                            elif not ok_pull:
                                self.signals.log.emit(f"Pull failed: {out_pull}", "#f38ba8")
                                success = False
                                break
                            else:
                                self.signals.log.emit("Merge successful, retrying push...", "#f9e2af")
                                ok_push, out_push = gm.push(repo)
                                if not ok_push:
                                    self.signals.log.emit(f"Retry push failed: {out_push}", "#f38ba8")
                                    hint = gm.explain_push_error(out_push)
                                    if hint:
                                        self.signals.log.emit(hint, "#f38ba8")
                                        final_message = hint
                                    success = False
                                    break
                                else:
                                    self.signals.log.emit(out_push, "#a6e3a1")
                                    pushed = True
                        else:
                            if step == "push":
                                hint = gm.explain_push_error(out)
                                if hint:
                                    final_message = hint
                            success = False
                            break

                if success and pushed:
                    ok_v, verify_msg = gm.verify_published(repo, bare_path=bare_path)
                    color = "#a6e3a1" if ok_v else "#f38ba8"
                    self.signals.log.emit(verify_msg, color)
                    if ok_v:
                        self.signals.banner.emit(
                            "remote", verify_msg, "", "✅")
                        if commit_hash:
                            sync_state.record_server_head(commit_hash)
                        if role == "main":
                            ok_m, msg_m = gm.update_server_mirror(self.config)
                            self.signals.log.emit(msg_m, "#a6e3a1" if ok_m else "#f38ba8")
                            self.signals.peer_sync.emit("", "", commit_hash or "")
                    else:
                        self.signals.banner.emit(
                            "local", verify_msg, "Retry", "❌")
                        success = False
                        final_message = verify_msg
                elif success and not pushed:
                    self.signals.log.emit(
                        "ℹ️ Committed locally — no remote push (check origin)",
                        "#f9e2af")
                    final_message = "Committed locally (not pushed to server)"

                if success:
                    hostname = socket.gethostname()
                    safe_hash = commit_hash if commit_hash else "local"

                    if role == "client" and remote_ip:
                        notify_msg = f"PUSH_NOTIFY:{hostname}:{safe_hash}:{msg}"
                        self.signals.log.emit(
                            f"📡 Sending push notification to Main ({remote_ip})…", "#a6adc8")
                        ok_n, out_n = send_message(remote_ip, notify_msg)
                        if ok_n:
                            self.signals.log.emit("✅ Main device notified", "#a6e3a1")
                        else:
                            self.signals.log.emit(
                                f"⚠️ Could not notify Main: {out_n}", "#f9e2af")
                    elif role == "main":
                        devices = list(self.device_panel.devices.keys())
                        if not devices and hasattr(self, "main_window"):
                            devices = list(self.main_window.device_panel.devices.keys())
                        if devices:
                            commit_notify = f"COMMIT_NOTIFY:{hostname}:{safe_hash}:{msg}"
                            for peer_ip in devices:
                                self.signals.log.emit(
                                    f"📡 Alerting client {peer_ip}…", "#a6adc8")
                                ok_n, out_n = send_message(peer_ip, commit_notify)
                                if ok_n:
                                    self.signals.log.emit(
                                        f"✅ Alert delivered to {peer_ip}", "#a6e3a1")
                                else:
                                    self.signals.log.emit(
                                        f"⚠️ Could not reach {peer_ip}: {out_n}", "#f9e2af")
                        else:
                            self.signals.log.emit(
                                "ℹ️ No clients in device list to alert", "#6c7086")

                if not success and final_message == "Commit & Push complete":
                    final_message = "Failed during processing"

                self.signals.done.emit(success, final_message)
                self.signals.popup.emit(success, final_message)

            finally:
                self._is_syncing = False

        threading.Thread(target=_r, daemon=True).start()

    def _do_pull(self, auto=False):
        repo      = self.config.get("repo_path", "")
        remote_ip = self.config.get("remote_ip", "")
        safe_name = self.config.get("safe_name", "")

        if not auto:
            self._log("── 📥 Receiving latest… ──", "#a6e3a1")

        role = self.config.get("role", "")

        def _r():
            if remote_ip and safe_name:
                gm.fix_remote(repo, remote_ip, safe_name)
            ok, out = gm.pull(repo, role=role, config=self.config)
            self.signals.log.emit(out, "#a6e3a1" if ok else "#f38ba8")

            if ok:
                import subprocess
                res = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=repo, capture_output=True, text=True, timeout=10)
                head = res.stdout.strip() if res.returncode == 0 else "?"
                msg = f"Received latest @ {head}"
                self.signals.popup.emit(True, msg)
                hostname = socket.gethostname()
                if role == "client" and remote_ip:
                    ack = f"PULL_ACK:{hostname}:{head}"
                    self.signals.log.emit(
                        f"📡 Confirming sync to Main ({remote_ip})…", "#a6adc8")
                    ok_a, out_a = send_message(remote_ip, ack)
                    if ok_a:
                        self.signals.log.emit(
                            f"✅ Main notified: synced @ {head}", "#a6e3a1")
                    else:
                        self.signals.log.emit(
                            f"⚠️ Could not confirm to Main: {out_a}", "#f9e2af")
                self.signals.done.emit(True, msg)
            elif gm.get_conflicts(repo):
                self.signals.conflict.emit()
            else:
                self.signals.done.emit(False, out)

        threading.Thread(target=_r, daemon=True).start()

    def _do_revert(self):
        repo = self.config.get("repo_path", "")
        if not repo: return

        # Get last 5 commits
        import subprocess
        try:
            res = subprocess.run(
                ["git", "log", "-5", "--format=%h  [ %cd ]  %s", "--date=format:%Y-%m-%d %H:%M"],
                cwd=repo, capture_output=True, text=True, check=True
            )
            commits = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to get commits:\n{e}")
            return

        if not commits:
            QMessageBox.information(self, "No Commits", "There are no commits to revert to.")
            return

        from PyQt6.QtWidgets import QInputDialog
        item, ok = QInputDialog.getItem(
            self, "Select Commit",
            "Select the commit you want to revert to:\n(All changes AFTER it will be undone)",
            commits, 0, False
        )
        
        if not ok or not item:
            return

        commit_hash = item.split()[0]
        
        r = QMessageBox.question(
            self, "Confirm Revert",
            f"Are you sure you want to revert to: {commit_hash}?\n\n"
            "This will permanently undo all changes made after this commit.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if r != QMessageBox.StandardButton.Yes:
            return

        self._log(f"── ↩ Reverting to {commit_hash}… ──", "#f38ba8")

        def _r():
            ok, out = gm.revert_to(repo, commit_hash)
            self.signals.log.emit(out, "#a6e3a1" if ok else "#f38ba8")
            self.signals.done.emit(ok, out)

        threading.Thread(target=_r, daemon=True).start()
        self.commit_msg.clear()

    # ── Status display ────────────────────────────────────────────────────────
    def _show_status(self):
        if not self.config:
            return
        repo = self.config.get("repo_path", "")

        def _r():
            try:
                # Status only — fast
                status = gm.get_status(repo)
                self.signals.log.emit("── Git Status ──", "#89b4fa")
                if status and status != "Clean — no changes":
                    # Show only first 20 lines to avoid freeze
                    lines = status.split("\n")[:20]
                    for l in lines:
                        self.signals.log.emit(l, "#a6adc8")
                    if len(status.split("\n")) > 20:
                        self.signals.log.emit(
                            f"  ... and {len(status.split(chr(10)))-20} more files",
                            "#6c7086")
                else:
                    self.signals.log.emit("✅ Clean — no uncommitted changes", "#a6adc8")

                # History — fast
                history = gm.get_history(repo, limit=5)
                self.signals.log.emit("── Recent Commits ──", "#89b4fa")
                if history:
                    for e in history:
                        self.signals.log.emit(
                            f"  [{e['hash']}] {e['message']}  •  "
                            f"{e['author']}  •  {e['time']}",
                            "#a6adc8")
                else:
                    self.signals.log.emit("  No commits yet", "#6c7086")

            except Exception as e:
                self.signals.log.emit(f"Status error: {e}", "#f38ba8")

        threading.Thread(target=_r, daemon=True).start()

    # ── on done ───────────────────────────────────────────────────────────────
    def _show_popup(self, success, message):
        """Show popup on main thread"""
        if success:
            QMessageBox.information(self, "✅ Done", message)
        else:
            QMessageBox.critical(self, "❌ Failed", message)

    def _on_done(self, success, message):
        if hasattr(self, "commit_push_btn"):
            self.commit_push_btn.setEnabled(True)
            self._update_change_badge(0)
            self.commit_msg.clear()

        if success:
            self._last_local_count = 0
            self._log("─" * 50, "#313244")
            self._log("✅  SUCCESS", "#a6e3a1")
            self._log(message, "#a6e3a1")
            self._log("─" * 50, "#313244")
        else:
            self._log("─" * 50, "#313244")
            self._log("❌  FAILED", "#f38ba8")
            self._log(message, "#f38ba8")
            self._log("─" * 50, "#313244")
        # Show popup via signal (safe on main thread)
        self._show_status()

    def _handle_conflict(self):
        repo = self.config.get("repo_path", "")
        conflicts = gm.get_conflicts(repo)
        if not conflicts:
            return
            
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Merge Conflict Detected")
        msg.setText("Your changes conflict with teammate's changes in:\n\n" + "\n".join(conflicts))
        msg.setInformativeText("How would you like to resolve this?")
        
        btn_mine = msg.addButton("Keep My Changes", QMessageBox.ButtonRole.AcceptRole)
        btn_theirs = msg.addButton("Keep Teammate's Changes", QMessageBox.ButtonRole.RejectRole)
        btn_abort = msg.addButton("Abort Merge", QMessageBox.ButtonRole.DestructiveRole)
        
        msg.exec()
        
        if msg.clickedButton() == btn_mine:
            self._log("Resolving conflicts: Keeping Mine", "#f9e2af")
            def _r():
                ok, out = gm.resolve_conflict(repo, "ours")
                if ok: gm.push(repo)
                self.signals.done.emit(ok, "Resolved conflicts (kept mine)" if ok else out)
            threading.Thread(target=_r, daemon=True).start()
        elif msg.clickedButton() == btn_theirs:
            self._log("Resolving conflicts: Keeping Theirs", "#f9e2af")
            def _r():
                ok, out = gm.resolve_conflict(repo, "theirs")
                if ok: gm.push(repo)
                self.signals.done.emit(ok, "Resolved conflicts (kept theirs)" if ok else out)
            threading.Thread(target=_r, daemon=True).start()
        else:
            self._log("Aborting merge", "#f38ba8")
            import subprocess
            subprocess.run(["git", "merge", "--abort"], cwd=repo)
            self.signals.done.emit(False, "Merge aborted by user.")
