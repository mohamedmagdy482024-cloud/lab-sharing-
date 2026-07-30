import os
import tempfile
import shutil
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QFrame,
    QInputDialog
)
from PyQt6.QtCore import pyqtSignal, QObject

from gui.progress_dialog import ProgressDialog
from core.transfer import send_folder, start_receiver
from core.utils import format_size, get_folder_size, count_files
from core.logger import logger, get_log_path
from core.messaging import send_message


class TransferSignals(QObject):
    progress        = pyqtSignal(int, int, str)
    done            = pyqtSignal(bool, str)
    speed           = pyqtSignal(float)
    message_result  = pyqtSignal(bool, str, str)  # success, peer_name, error_msg


class FileTransferTab(QWidget):
    def __init__(self, device_panel, log_panel=None):
        super().__init__()
        self.device_panel  = device_panel
        self.log_panel     = log_panel
        self.selected_path = None
        self.signals       = TransferSignals()
        self._tmp_to_clean = None
        self._build_ui()
        self._connect_signals()

    def _log(self, msg, color="#a6adc8"):
        logger.info(msg)
        if self.log_panel:
            self.log_panel.append(msg, color)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.setAlignment(layout.alignment())

        # ── Selected path card ───────────────────────────────
        card = QFrame()
        card.setStyleSheet("QFrame { background-color:#181825; border-radius:8px; }")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(5)

        lbl_title = QLabel("📎  Selected File or Folder")
        lbl_title.setStyleSheet("color:#89b4fa; font-size:12px; font-weight:bold;")
        cl.addWidget(lbl_title)

        self.path_label = QLabel("Nothing selected")
        self.path_label.setStyleSheet("color:#6c7086; font-size:11px;")
        self.path_label.setWordWrap(True)
        cl.addWidget(self.path_label)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color:#a6e3a1; font-size:10px;")
        cl.addWidget(self.info_label)

        # Browse buttons row
        browse_row = QHBoxLayout()
        browse_row.setSpacing(8)

        btn_file = QPushButton("📄  Select File")
        btn_file.setStyleSheet("""
            QPushButton {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 6px 14px; font-size: 12px;
            }
            QPushButton:hover { background-color: #45475a; }
        """)
        btn_file.clicked.connect(self._browse_file)
        browse_row.addWidget(btn_file)

        btn_folder = QPushButton("📁  Select Folder")
        btn_folder.setStyleSheet(btn_file.styleSheet())
        btn_folder.clicked.connect(self._browse_folder)
        browse_row.addWidget(btn_folder)

        cl.addLayout(browse_row)
        layout.addWidget(card)

        # ── Send / Receive buttons ───────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.send_btn = QPushButton("📤  Send to Device")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa; color: #1e1e2e;
                border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #b4d0fa; }
        """)
        self.send_btn.clicked.connect(self._send)
        action_row.addWidget(self.send_btn)

        self.receive_btn = QPushButton("📥  Receive Files")
        self.receive_btn.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1; color: #1e1e2e;
                border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #c6f3c1; }
        """)
        self.receive_btn.clicked.connect(self._receive)
        action_row.addWidget(self.receive_btn)

        self.msg_btn = QPushButton("💬  Send Message")
        self.msg_btn.setStyleSheet("""
            QPushButton {
                background-color: #f9e2af; color: #1e1e2e;
                border: none; border-radius: 6px;
                padding: 8px 16px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #faeabf; }
        """)
        self.msg_btn.clicked.connect(self._send_message)
        action_row.addWidget(self.msg_btn)

        layout.addLayout(action_row)
        layout.addStretch()

    def _connect_signals(self):
        self.signals.progress.connect(self._on_progress)
        self.signals.done.connect(self._on_done)
        self.signals.speed.connect(self._on_speed)
        self.signals.message_result.connect(self._on_message_result)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a File", os.path.expanduser("~"))
        if path:
            self._set_path(path)

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select a Folder", os.path.expanduser("~"))
        if path:
            self._set_path(path)

    def _set_path(self, path):
        self.selected_path = path
        if os.path.isfile(path):
            size = os.path.getsize(path)
            self.path_label.setText(path)
            self.info_label.setText(f"File — {format_size(size)}")
            self._log(f"📄 File selected: {os.path.basename(path)} ({format_size(size)})", "#a6adc8")
        else:
            size  = get_folder_size(path)
            count = count_files(path)
            self.path_label.setText(path)
            self.info_label.setText(f"Folder — {count} files — {format_size(size)}")
            self._log(f"📁 Folder selected: {path} ({count} files, {format_size(size)})", "#a6adc8")

    def _send(self):
        if not self.selected_path:
            QMessageBox.warning(self, "Nothing Selected",
                "Please select a file or folder first.")
            return
        ip   = self.device_panel.get_selected_ip()
        name = self.device_panel.get_selected_name()
        if not ip:
            QMessageBox.warning(self, "No Device",
                "Please select a device from the left list.")
            return

        self._log(f"=== SEND START → {name} ({ip}) ===", "#89b4fa")
        self.progress_dialog = ProgressDialog(f"Sending to {name}…", self)
        self.progress_dialog.show()

        if os.path.isfile(self.selected_path):
            tmp = tempfile.mkdtemp()
            shutil.copy2(self.selected_path, tmp)
            send_path = tmp
            self._tmp_to_clean = tmp
        else:
            send_path = self.selected_path
            self._tmp_to_clean = None

        send_folder(
            send_path, ip,
            progress_callback=lambda c, t, p: self.signals.progress.emit(c, t, p),
            done_callback    =lambda ok, m:   self.signals.done.emit(ok, m),
            speed_callback   =lambda s:       self.signals.speed.emit(s),
        )

    def _receive(self):
        save_path = QFileDialog.getExistingDirectory(
            self, "Save received files to…", os.path.expanduser("~"))
        if not save_path:
            return
        self._log(f"=== RECEIVE — saving to {save_path} ===", "#89b4fa")
        self._log("Waiting for sender…", "#f9e2af")
        self.progress_dialog = ProgressDialog("⏳ Waiting for sender…", self)
        self.progress_dialog.show()

        start_receiver(
            save_path,
            progress_callback=lambda c, t, p: self.signals.progress.emit(c, t, p),
            done_callback    =lambda ok, m:   self.signals.done.emit(ok, m),
            speed_callback   =lambda s:       self.signals.speed.emit(s),
        )

    def _on_progress(self, current, total, path):
        if hasattr(self, "progress_dialog"):
            pct = int((current / total) * 100)
            self.progress_dialog.update_progress(
                pct, f"[{current}/{total}] {os.path.basename(path)}")
        self._log(f"[{current}/{total}] {os.path.basename(path)}", "#a6adc8")

    def _on_speed(self, speed):
        if hasattr(self, "progress_dialog"):
            self.progress_dialog.update_speed(speed)

    def _on_done(self, success, message):
        if hasattr(self, "progress_dialog"):
            self.progress_dialog.close()
        if self._tmp_to_clean:
            shutil.rmtree(self._tmp_to_clean, ignore_errors=True)
            self._tmp_to_clean = None
        if success:
            self._log("=== COMPLETE ✅ ===", "#a6e3a1")
            self._log(message, "#a6e3a1")
            QMessageBox.information(self, "Done ✅", message)
        else:
            self._log(f"ERROR: {message}", "#f38ba8")
            QMessageBox.critical(self, "Error ❌",
                f"{message}\n\n📋 Log: {get_log_path()}")

    def _send_message(self):
        ip = self.device_panel.get_selected_ip()
        name = self.device_panel.get_selected_name()
        if not ip:
            QMessageBox.warning(self, "No Device", "Please select a device from the list first.")
            return

        text, ok = QInputDialog.getMultiLineText(self, "Send Message", f"Type your message for {name}:")
        if not (ok and text.strip()):
            return

        # Disable button while sending so user gets feedback and can't double-send
        self.msg_btn.setEnabled(False)
        self.msg_btn.setText("💬  Sending…")
        self._log(f"💬 Sending message to {name} ({ip})…", "#f9e2af")

        # Run the blocking network call in a background thread to avoid freezing the GUI
        def _worker():
            success, err = send_message(ip, text.strip())
            self.signals.message_result.emit(success, name, err)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_message_result(self, success, name, err):
        """Called on the main thread via signal after the background send completes."""
        self.msg_btn.setEnabled(True)
        self.msg_btn.setText("💬  Send Message")
        if success:
            self._log(f"✅ Message sent to {name}", "#a6e3a1")
            QMessageBox.information(self, "Message Sent ✅", f"Message delivered to {name}.")
        else:
            self._log(f"❌ Message failed: {err}", "#f38ba8")
            QMessageBox.critical(
                self, "Send Error",
                f"Could not send message to {name}:\n\n{err}\n\n"
                f"💡 Make sure Lab Sharing is running on the other device."
            )
