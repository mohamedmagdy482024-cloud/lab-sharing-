from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from core.logger import get_log_path
import os


class LogPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._last_pos = 0      # track file position not size
        
        log_path = get_log_path()
        if os.path.exists(log_path):
            self._last_pos = os.path.getsize(log_path)
            
        self._in_memory = []    # keep ALL messages in memory
        self._build_ui()
        self._start_auto_refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background-color:#181825;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 6, 8, 6)
        hl.setSpacing(6)

        title = QLabel("📋 Live Log")
        title.setStyleSheet(
            "color:#f9e2af; font-size:12px; font-weight:bold;")
        hl.addWidget(title)
        hl.addStretch()

        copy_btn = QPushButton("📋 Copy All")
        copy_btn.setToolTip("Copy entire log to clipboard")
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color:#313244; color:#cdd6f4;
                border:none; border-radius:4px;
                padding:3px 10px; font-size:11px;
            }
            QPushButton:hover { background-color:#45475a; }
        """)
        copy_btn.clicked.connect(self._copy_all)
        hl.addWidget(copy_btn)

        clear_btn = QPushButton("🗑 Clear")
        clear_btn.setToolTip("Clear log display")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color:#313244; color:#cdd6f4;
                border:none; border-radius:4px;
                padding:3px 10px; font-size:11px;
            }
            QPushButton:hover { background-color:#f38ba8; color:#1e1e2e; }
        """)
        clear_btn.clicked.connect(self._clear)
        hl.addWidget(clear_btn)

        layout.addWidget(header)

        # Log area
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Ubuntu Mono", 9))
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color:#11111b;
                color:#a6adc8;
                border:none;
                padding:8px;
                font-family:'Ubuntu Mono','Courier New',monospace;
                font-size:10px;
            }
        """)
        layout.addWidget(self.log_view)

    def _start_auto_refresh(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._refresh_from_file)
        self.timer.start(800)

    def _refresh_from_file(self):
        """Read only NEW lines from log file since last read"""
        log_path = get_log_path()
        if not os.path.exists(log_path):
            return
        try:
            with open(log_path, "r", errors="replace") as f:
                f.seek(self._last_pos)
                new_lines = f.readlines()
                self._last_pos = f.tell()

            for line in new_lines:
                line = line.rstrip()
                if line:
                    self._in_memory.append(line)
                    self._append_colored(line)

            if new_lines:
                self._scroll_bottom()
        except Exception:
            pass

    def _append_colored(self, line):
        if "❌" in line or "FAILED" in line or "[ERROR]" in line:
            color = "#f38ba8"
        elif "✅" in line or "SUCCESS" in line or "successful" in line.lower():
            color = "#a6e3a1"
        elif "WARNING" in line or "[WARNING]" in line:
            color = "#f9e2af"
        elif "===" in line or "──" in line or "─" * 5 in line:
            color = "#89b4fa"
        elif "⬆" in line or "⬇" in line or "💾" in line or "↩" in line:
            color = "#f9e2af"
        else:
            color = "#a6adc8"
        self.log_view.setTextColor(QColor(color))
        self.log_view.append(line)

    def append(self, text, color="#a6adc8"):
        """Append a message directly — keeps it in memory too"""
        self._in_memory.append(text)
        self.log_view.setTextColor(QColor(color))
        self.log_view.append(text)
        self._scroll_bottom()

    def _scroll_bottom(self):
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_all(self):
        """Copy ALL log content including what's not visible"""
        all_text = "\n".join(self._in_memory)
        if not all_text:
            all_text = self.log_view.toPlainText()
        if all_text:
            QApplication.clipboard().setText(all_text)
            self.append("── ✅ Full log copied to clipboard ──", "#89b4fa")

    def _clear(self):
        """Clear display only — memory stays for Copy All"""
        self.log_view.clear()
        self.append("── Log display cleared ──", "#6c7086")
