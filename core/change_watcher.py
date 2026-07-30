"""
core/change_watcher.py
~~~~~~~~~~~~~~~~~~~~~~
Watches a git repo directory for local file-system changes using watchdog.

Key design decisions:
  - Excludes .git/ to avoid infinite loops during git operations.
  - 2-second debounce: waits until file activity settles before running git status.
  - Uses a threading.Timer for debounce (reset on each new event).
  - Falls back to 60-second polling if watchdog is not installed.
  - Calls on_change(changed_files: list[str]) from a daemon thread;
    the GUI must relay this via a Qt signal.
"""

import os
import threading
import sys
from core.logger import logger

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    logger.warning("watchdog not installed — falling back to 60s polling")


DEBOUNCE_SECONDS = 2.0


class _RepoEventHandler(FileSystemEventHandler):
    """Handles raw watchdog events, debouncing and ignoring .git/ internals."""

    def __init__(self, repo_path, on_settled):
        super().__init__()
        self._repo_path = os.path.normpath(repo_path)
        self._git_dir = os.path.normpath(os.path.join(self._repo_path, ".git"))
        self._on_settled = on_settled
        self._timer = None
        self._lock = threading.Lock()

    def _is_git_internal(self, path):
        norm = os.path.normcase(os.path.normpath(path))
        git_dir = os.path.normcase(self._git_dir)
        return norm.startswith(git_dir + os.sep) or norm == git_dir

    def _schedule(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._on_settled)
            self._timer.daemon = True
            self._timer.start()

    def on_modified(self, event):
        if not event.is_directory and not self._is_git_internal(event.src_path):
            self._schedule()

    def on_created(self, event):
        if not event.is_directory and not self._is_git_internal(event.src_path):
            self._schedule()

    def on_deleted(self, event):
        if not event.is_directory and not self._is_git_internal(event.src_path):
            self._schedule()

    def on_moved(self, event):
        if not event.is_directory and not self._is_git_internal(event.src_path):
            self._schedule()


class ChangeWatcher:
    """
    Monitors a git working directory for uncommitted local changes.

    Usage:
        watcher = ChangeWatcher(
            repo_path="/path/to/repo",
            on_change=lambda files: qt_signal.emit(files),
            is_busy=lambda: git_op_in_progress,
        )
        watcher.start()
        # ... on shutdown ...
        watcher.stop()
    """

    def __init__(self, repo_path, on_change, is_busy=None):
        self._repo_path = os.path.normpath(repo_path)
        self._on_change = on_change
        self._is_busy   = is_busy or (lambda: False)
        self._observer  = None
        self._fallback_timer = None
        # OneDrive / cloud paths: filesystem events are often delayed or missing
        self._use_fast_poll = (
            sys.platform == "win32"
            or "onedrive" in self._repo_path.lower()
        )

    def start(self):
        if _WATCHDOG_AVAILABLE:
            self._start_watchdog()
        else:
            self._start_fallback()
        # Always run git-status polling as backup (critical on OneDrive / Windows)
        if self._use_fast_poll and self._observer is not None:
            self._start_fallback(interval=15.0)

    def stop(self):
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
            self._observer = None
        if self._fallback_timer:
            self._fallback_timer.cancel()
            self._fallback_timer = None
        logger.info("ChangeWatcher stopped")

    # ── watchdog path ────────────────────────────────────────────────────────

    def _start_watchdog(self):
        try:
            handler = _RepoEventHandler(
                repo_path=self._repo_path,
                on_settled=self._check_status,
            )
            self._observer = Observer()
            # Recursive to catch changes in subdirectories
            self._observer.schedule(handler, self._repo_path, recursive=True)
            self._observer.daemon = True
            self._observer.start()
            logger.info(f"ChangeWatcher (watchdog) on: {self._repo_path}")
        except Exception as e:
            logger.error(f"ChangeWatcher watchdog failed, using fallback: {e}")
            self._observer = None
            interval = 15.0 if self._use_fast_poll else 60.0
            self._start_fallback(interval=interval)

    # ── fallback 60s polling ─────────────────────────────────────────────────

    def _start_fallback(self, interval=60.0):
        self._poll_interval = interval
        self._schedule_fallback()
        logger.info(
            f"ChangeWatcher ({interval:.0f}s git-status poll) on: {self._repo_path}")

    def _schedule_fallback(self):
        self._fallback_timer = threading.Timer(self._poll_interval, self._fallback_tick)
        self._fallback_timer.daemon = True
        self._fallback_timer.start()

    def _fallback_tick(self):
        self._check_status()
        self._schedule_fallback()

    # ── shared status check ──────────────────────────────────────────────────

    def _check_status(self):
        """Run git status after debounce settles. Skip if a git op is running."""
        if self._is_busy():
            return
        try:
            import subprocess
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=self._repo_path,
                capture_output=True, text=True, timeout=10
            )
            lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
            if lines:
                logger.info(f"ChangeWatcher: {len(lines)} local change(s)")
                self._on_change(lines)
        except Exception as e:
            logger.error(f"ChangeWatcher status check error: {e}")
