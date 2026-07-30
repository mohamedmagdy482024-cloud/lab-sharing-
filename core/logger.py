import logging
import os
import sys
from datetime import datetime

LOG_DIR = os.path.expanduser("~/.lab-sharing")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "lab-sharing.log")


class SafeUtf8StreamHandler(logging.StreamHandler):
    """Console handler that never crashes on emoji / Unicode (Windows cp1252)."""

    def emit(self, record):
        try:
            msg = self.format(record) + self.terminator
            if hasattr(self.stream, "buffer"):
                self.stream.buffer.write(msg.encode("utf-8", errors="replace"))
                self.stream.flush()
            else:
                self.stream.write(msg.encode("ascii", errors="replace").decode("ascii"))
                self.flush()
        except Exception:
            self.handleError(record)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        SafeUtf8StreamHandler(sys.stdout),
    ],
    force=True,
)

logger = logging.getLogger("lab-sharing")


def get_log_path():
    return LOG_FILE
