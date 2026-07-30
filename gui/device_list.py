from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
)
from PyQt6.QtCore import Qt


class DeviceListPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.devices = {}
        self.on_refresh = None
        self.on_log = None  # callback to write to log panel
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("  📡 Devices")
        header.setStyleSheet("""
            background-color: #181825;
            color: #89b4fa;
            font-size: 13px;
            font-weight: bold;
            padding: 10px 16px;
        """)
        layout.addWidget(header)

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: none;
                border-bottom: 1px solid #45475a;
                border-radius: 0px;
                padding: 7px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #45475a; }
        """)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        layout.addWidget(self.refresh_btn)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #1e1e2e;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 16px;
                border-bottom: 1px solid #313244;
                color: #cdd6f4;
                font-size: 12px;
            }
            QListWidget::item:selected {
                background-color: #313244;
                color: #89b4fa;
            }
            QListWidget::item:hover { background-color: #27273a; }
        """)
        layout.addWidget(self.list_widget)

    def _on_refresh_clicked(self):
        self.refresh_btn.setText("🔄 Searching...")
        self.refresh_btn.setEnabled(False)
        if self.on_refresh:
            self.on_refresh()
        if self.on_log:
            self.on_log("🔄 Refreshing — scanning all interfaces...", "#f9e2af")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(3000, self._reset_refresh_btn)

    def _reset_refresh_btn(self):
        self.refresh_btn.setText("🔄 Refresh")
        self.refresh_btn.setEnabled(True)

    def add_device(self, ip, name):
        if ip not in self.devices:
            self.devices[ip] = name
            item = QListWidgetItem(f"🖥️  {name}\n    {ip}")
            item.setData(Qt.ItemDataRole.UserRole, ip)
            self.list_widget.addItem(item)
            if self.on_log:
                self.on_log(f"✅ Device found: {name} ({ip})", "#a6e3a1")

    def remove_device(self, ip):
        if ip in self.devices:
            name = self.devices.pop(ip)
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == ip:
                    self.list_widget.takeItem(i)
                    break
            if self.on_log:
                self.on_log(f"❌ Device lost: {name} ({ip})", "#f38ba8")

    def get_selected_ip(self):
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def get_selected_name(self):
        item = self.list_widget.currentItem()
        if item:
            return self.devices.get(item.data(Qt.ItemDataRole.UserRole), "Unknown")
        return None
