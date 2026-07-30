from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStatusBar, QFrame, QSplitter, QPushButton,
    QStackedWidget
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt

from gui.device_list import DeviceListPanel
from gui.transfer_panel import FileTransferTab
from gui.git_panel import GitPanel
from gui.log_panel import LogPanel
from gui.guide_dialog import GuideDialog
from core.discovery import DeviceDiscovery
from core.messaging import start_message_listener
from core import git_manager as gm
from core import sync_state
from core.platform import notify_user
import socket

# ── shared tab button style ──────────────────────────────────
def _tab_style(active: bool) -> str:
    if active:
        return """
            QPushButton {
                background-color: transparent;
                color: #cdd6f4;
                border: none;
                border-bottom: 2px solid #89b4fa;
                border-radius: 0;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: bold;
            }
        """
    return """
        QPushButton {
            background-color: transparent;
            color: #6c7086;
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0;
            padding: 6px 18px;
            font-size: 12px;
        }
        QPushButton:hover { color: #a6adc8; }
    """

GUIDE_STYLE = """
    QPushButton {
        background-color: transparent;
        color: #cba6f7;
        border: none;
        border-bottom: 2px solid transparent;
        border-radius: 0;
        padding: 6px 16px;
        font-size: 12px;
    }
    QPushButton:hover { color: #d4b4f8; }
"""


class Signals(QObject):
    device_found    = pyqtSignal(str, str)
    device_lost     = pyqtSignal(str, str)
    message_received = pyqtSignal(str, str)  # from_ip, text


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lab Sharing")
        self.setMinimumWidth(820)
        self.signals = Signals()
        self._apply_theme()
        self._build_ui()
        self._start_discovery()

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color:#1e1e2e; color:#cdd6f4;
                font-family:'Segoe UI', Ubuntu, sans-serif; }
            QLabel#title   { font-size:20px; font-weight:bold; color:#89b4fa; }
            QLabel#subtitle{ font-size:11px; color:#6c7086; }
            QStatusBar     { background-color:#181825; color:#6c7086; font-size:11px; }
            QFrame#divider { background-color:#313244; }
            QSplitter::handle          { background-color:#313244; }
            QSplitter::handle:vertical { height:1px; }
        """)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ───────────────────────────────────────────
        hdr = QWidget()
        hdr.setStyleSheet("background-color:#181825;")
        hdr.setFixedHeight(54)
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(18, 7, 18, 7)
        hl.setSpacing(2)
        title = QLabel("🔗 Lab Sharing"); title.setObjectName("title")
        self.subtitle = QLabel(f"This device: {socket.gethostname()}")
        self.subtitle.setObjectName("subtitle")
        hl.addWidget(title); hl.addWidget(self.subtitle)
        root.addWidget(hdr)

        hdiv = QFrame(); hdiv.setObjectName("divider"); hdiv.setFixedHeight(1)
        root.addWidget(hdiv)

        # ── Vertical splitter: top + log ─────────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)

        # ── Top: devices | right panels ──────────────────────
        top = QWidget()
        top_h = QHBoxLayout(top)
        top_h.setContentsMargins(0, 0, 0, 0)
        top_h.setSpacing(0)

        # Left devices panel
        self.device_panel = DeviceListPanel()
        self.device_panel.setFixedWidth(230)
        self.device_panel.on_refresh = self._do_refresh
        top_h.addWidget(self.device_panel)

        vdiv = QFrame(); vdiv.setObjectName("divider"); vdiv.setFixedWidth(1)
        top_h.addWidget(vdiv)

        # Right: tab bar + stacked content
        right = QWidget()
        right.setStyleSheet("background-color:#1e1e2e;")
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(0)

        # Tab bar
        tab_bar = QWidget()
        tab_bar.setStyleSheet("background-color:#181825; border-bottom:1px solid #313244;")
        tab_bar.setFixedHeight(36)
        tb = QHBoxLayout(tab_bar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(0)

        self.btn_transfer = QPushButton("📁  Transfer")
        self.btn_git      = QPushButton("🔀  Git Sync")
        self.btn_guide    = QPushButton("📖  Guide")

        self.btn_transfer.setStyleSheet(_tab_style(True))
        self.btn_git.setStyleSheet(_tab_style(False))
        self.btn_guide.setStyleSheet(GUIDE_STYLE)

        self.btn_transfer.clicked.connect(lambda: self._switch(0))
        self.btn_git.clicked.connect(lambda: self._switch(1))
        self.btn_guide.clicked.connect(self._show_guide)

        tb.addWidget(self.btn_transfer)
        tb.addWidget(self.btn_git)
        tb.addWidget(self.btn_guide)
        tb.addStretch()
        right_v.addWidget(tab_bar)

        # Stacked content — shrinks to fit content
        self.stack = QStackedWidget()
        self.file_tab = FileTransferTab(self.device_panel)
        self.git_tab  = GitPanel(self.device_panel)
        self.stack.addWidget(self.file_tab)  # 0
        self.stack.addWidget(self.git_tab)   # 1
        right_v.addWidget(self.stack)

        top_h.addWidget(right)
        vsplit.addWidget(top)

        # ── Bottom: Live Log full width ───────────────────────
        self.log_panel = LogPanel()
        self.log_panel.setFixedHeight(160)
        vsplit.addWidget(self.log_panel)

        vsplit.setStretchFactor(0, 1)
        vsplit.setStretchFactor(1, 0)

        root.addWidget(vsplit)

        # Wire log panel into sub-panels
        self.file_tab.log_panel  = self.log_panel
        self.git_tab.log_panel   = self.log_panel
        self.device_panel.on_log = self.log_panel.append

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("🟡 Starting…")

        self.signals.device_found.connect(self._on_device_found)
        self.signals.device_lost.connect(self._on_device_lost)
        self.signals.message_received.connect(self._on_message_received)

    def _switch(self, index: int):
        self.stack.setCurrentIndex(index)
        self.btn_transfer.setStyleSheet(_tab_style(index == 0))
        self.btn_git.setStyleSheet(_tab_style(index == 1))

    def _show_guide(self):
        GuideDialog(self).exec()

    def _start_discovery(self):
        self.discovery = DeviceDiscovery(
            on_device_found=lambda ip, name: self.signals.device_found.emit(ip, name),
            on_device_lost =lambda ip, name: self.signals.device_lost.emit(ip, name),
        )
        self.discovery.start()
        local_ip = self.discovery.get_local_ip()
        self.subtitle.setText(
            f"This device: {socket.gethostname()}  |  IP: {local_ip}")
        self.status.showMessage(
            f"🟢 Ready — My IP: {local_ip} — Searching for devices…")
        self.log_panel.append("=== Lab Sharing Started ===", "#89b4fa")
        self.log_panel.append(f"My IP: {local_ip}", "#a6adc8")
        self.log_panel.append("Searching for devices on LAN & WiFi…", "#a6adc8")

        # Start the TCP message listener so other devices can send us messages
        start_message_listener(
            on_message_callback=lambda ip, msg: self.signals.message_received.emit(ip, msg)
        )
        self.log_panel.append("Message listener started (port 57323)", "#6c7086")

    def _do_refresh(self):
        for ip in list(self.device_panel.devices.keys()):
            self.device_panel.remove_device(ip)
        self.discovery.devices.clear()
        self.discovery.force_refresh()
        self.status.showMessage("🔄 Refreshing…")

    def _on_device_found(self, ip, name):
        self.device_panel.add_device(ip, name)
        self.status.showMessage(f"✅ Found: {name} ({ip})")

    def _on_device_lost(self, ip, name):
        self.device_panel.remove_device(ip)
        self.status.showMessage(f"❌ Lost: {name} ({ip})")

    def _on_message_received(self, from_ip, text):
        """Called on the main thread when a message arrives from another device."""
        if text.startswith("PULL_ACK:"):
            parts = text.split(":", 2)
            if len(parts) == 3:
                _, hostname, commit_hash = parts
                sync_state.record_pull_ack(from_ip, hostname, commit_hash)
                self.git_tab.signals.peer_sync.emit(from_ip, hostname, commit_hash)
                self.log_panel.append(
                    f"✅ {hostname} synced @ {commit_hash}", "#a6e3a1")
            return

        # Parse Git notifications
        if text.startswith("PUSH_NOTIFY:") or text.startswith("COMMIT_NOTIFY:"):
            parts = text.split(":", 3)
            if len(parts) == 4:
                prefix, hostname, commit_hash, msg = parts
                if prefix == "PUSH_NOTIFY":
                    self.git_tab.signals.banner.emit(
                        "remote", f"{hostname} pushed: {msg}", "Receive", "📥")
                    notify_user("Lab Sharing", f"{hostname} pushed: {msg}")
                else:
                    self.git_tab.signals.banner.emit(
                        "remote", f"Main updated: {msg}", "Receive", "📥")
                    notify_user("Lab Sharing", f"Main updated: {msg}")
                self.log_panel.append(
                    f"📡 Git change detected from {hostname}: {msg}", "#89b4fa")
                cfg = gm.load_config()
                if cfg and (cfg.get("auto_pull") or "off").lower() == "on":
                    self.log_panel.append("🔄 Auto-pull enabled — receiving…", "#a6adc8")
                    self.git_tab._do_pull(auto=True)
                return

        # Regular text message
        peer = self.device_panel.devices.get(from_ip, from_ip)
        self.log_panel.append(f"💬 Message from {peer}: {text}", "#f9e2af")
        self.status.showMessage(f"💬 New message from {peer}")
        
        from PyQt6.QtWidgets import QDialog, QTextEdit
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Message from {peer}")
        dlg.resize(400, 300)
        l = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(text)
        l.addWidget(te)
        dlg.exec()

    def closeEvent(self, event):
        self.discovery.stop()
        super().closeEvent(event)
