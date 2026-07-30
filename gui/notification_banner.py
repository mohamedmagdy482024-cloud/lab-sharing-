"""
gui/notification_banner.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
A non-blocking slide-in notification banner for the Git Sync panel.

Design:
  - Sits at the TOP of the git panel content area (inserted dynamically).
  - Shows an icon, a short message, an action button, and a dismiss [✕].
  - Auto-dismisses after `auto_dismiss_ms` milliseconds (default 60s).
  - Emits `dismissed` signal when closed (by user or timeout).
  - Styled with the app's Catppuccin Mocha palette.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import pyqtSignal, QTimer, Qt


# ── colour presets ────────────────────────────────────────────────────────────
STYLE_INFO   = ("#1e3a5f", "#89b4fa", "#89b4fa")   # bg, border, icon-colour
STYLE_WARN   = ("#3d2a00", "#f9e2af", "#f9e2af")   # local-changes (yellow)
STYLE_REMOTE = ("#1a3a1a", "#a6e3a1", "#a6e3a1")   # remote-changes (green)
STYLE_ERROR  = ("#3d1a1a", "#f38ba8", "#f38ba8")   # error (red)


class NotificationBanner(QWidget):
    """
    A single dismissible notification strip.

    Signals:
        dismissed()          — emitted when the banner closes for any reason.
        action_clicked()     — emitted when the action button is clicked.
    """

    dismissed     = pyqtSignal()
    action_clicked = pyqtSignal()

    def __init__(
        self,
        message:          str,
        action_label:     str  = "",
        icon:             str  = "💡",
        style                  = STYLE_INFO,
        auto_dismiss_ms:  int  = 60_000,
        parent=None,
    ):
        super().__init__(parent)
        bg, border, _ = style
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)
        self.setFixedHeight(44)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(10)

        # Icon
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"color:{border}; font-size:16px; background:transparent; border:none;")
        icon_lbl.setFixedWidth(22)
        row.addWidget(icon_lbl)

        # Message
        self._msg_lbl = QLabel(message)
        self._msg_lbl.setStyleSheet(f"color:{border}; font-size:12px; background:transparent; border:none;")
        self._msg_lbl.setWordWrap(False)
        row.addWidget(self._msg_lbl, stretch=1)

        # Action button (optional)
        if action_label:
            self._action_btn = QPushButton(action_label)
            self._action_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {border};
                    color: #1e1e2e;
                    border: none;
                    border-radius: 5px;
                    padding: 4px 12px;
                    font-size: 11px;
                    font-weight: bold;
                }}
                QPushButton:hover {{ opacity: 0.85; }}
            """)
            self._action_btn.setFixedHeight(28)
            self._action_btn.clicked.connect(self._on_action)
            row.addWidget(self._action_btn)

        # Dismiss button
        dismiss_btn = QPushButton("✕")
        dismiss_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #6c7086;
                border: none;
                font-size: 14px;
                padding: 0 4px;
            }
            QPushButton:hover { color: #cdd6f4; }
        """)
        dismiss_btn.setFixedSize(24, 24)
        dismiss_btn.clicked.connect(self.dismiss)
        row.addWidget(dismiss_btn)

        # Auto-dismiss timer
        if auto_dismiss_ms > 0:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self.dismiss)
            self._timer.start(auto_dismiss_ms)

    # ── public ───────────────────────────────────────────────────────────────

    def update_message(self, message: str):
        """Update the text without closing the banner."""
        self._msg_lbl.setText(message)

    def dismiss(self):
        self.hide()
        self.dismissed.emit()
        self.deleteLater()

    # ── private ──────────────────────────────────────────────────────────────

    def _on_action(self):
        self.action_clicked.emit()
        self.dismiss()


class BannerStack(QWidget):
    """
    Manages a vertical stack of up to MAX_BANNERS NotificationBanner widgets.
    Insert at the top of any QVBoxLayout:

        self.banner_stack = BannerStack(parent=self)
        layout.insertWidget(0, self.banner_stack)

    Then call:
        self.banner_stack.push(banner)
    """

    MAX_BANNERS = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = __import__('PyQt6.QtWidgets', fromlist=['QVBoxLayout']).QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._banners: list[NotificationBanner] = []
        self.hide()   # invisible until first banner

    def push(self, banner: NotificationBanner):
        """Add a banner to the stack. Drops the oldest if MAX_BANNERS exceeded."""
        if len(self._banners) >= self.MAX_BANNERS:
            self._banners[0].dismiss()

        self._banners.append(banner)
        self._layout.addWidget(banner)
        banner.dismissed.connect(lambda: self._remove(banner))
        self.show()

    def _remove(self, banner: NotificationBanner):
        if banner in self._banners:
            self._banners.remove(banner)
        if not self._banners:
            self.hide()
