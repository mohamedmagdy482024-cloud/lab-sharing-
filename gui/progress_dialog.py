from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt


class ProgressDialog(QDialog):
    def __init__(self, title="Transferring...", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lab Sharing")
        self.setFixedSize(420, 160)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { color: #cdd6f4; font-size: 13px; }
            QProgressBar {
                background-color: #313244;
                border-radius: 6px;
                height: 18px;
                text-align: center;
                color: #1e1e2e;
                font-weight: bold;
                font-size: 11px;
            }
            QProgressBar::chunk { background-color: #89b4fa; border-radius: 6px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(self.title_label)

        self.file_label = QLabel("Starting...")
        self.file_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        layout.addWidget(self.file_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.speed_label = QLabel("")
        self.speed_label.setStyleSheet("color: #a6e3a1; font-size: 11px; font-weight: bold;")
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.speed_label)

    def update_progress(self, percent, filename=""):
        self.progress_bar.setValue(percent)
        self.file_label.setText(filename)

    def update_speed(self, speed_mbps):
        if speed_mbps > 0:
            self.speed_label.setText(f"⚡ {speed_mbps:.1f} MB/s")
        else:
            self.speed_label.setText("")
