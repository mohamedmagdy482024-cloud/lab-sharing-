import sys
import traceback
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from gui.main_window import MainWindow
from core.logger import logger


def _exception_hook(exc_type, exc_value, exc_tb):
    """Log unhandled exceptions instead of silently crashing."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical(f"UNHANDLED EXCEPTION:\n{msg}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main():
    sys.excepthook = _exception_hook
    app = QApplication(sys.argv)
    app.setApplicationName("Lab Sharing")
    app.setOrganizationName("LabTools")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
