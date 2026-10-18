"""
Logging infrastructure for Luga Assist.
Provides rotating file logs, error logs, print redirection, and log inspection API.
"""
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional

from app.config import (
    LOGS_DIR,
    LOG_FILE,
    ERROR_LOG_FILE,
)

LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

class PrintTeeStream:
    """
    Tees output from print() / sys.stdout / sys.stderr into both
    the console and the rotating log file, preserving timestamps.
    """
    def __init__(self, original_stream, log_file_path: Path, is_err: bool = False):
        self.original_stream = original_stream
        self.log_file_path = log_file_path
        self.is_err = is_err
        self._buffer = ""

    def write(self, message: str):
        if self.original_stream:
            try:
                self.original_stream.write(message)
                self.original_stream.flush()
            except Exception:
                pass

        if not message:
            return

        # Write to log file
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(message)
        except Exception:
            pass

        if self.is_err:
            try:
                with open(ERROR_LOG_FILE, "a", encoding="utf-8") as ef:
                    ef.write(message)
            except Exception:
                pass

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        if self.original_stream and hasattr(self.original_stream, "isatty"):
            try:
                return self.original_stream.isatty()
            except Exception:
                return False
        return False

    def fileno(self):
        if self.original_stream and hasattr(self.original_stream, "fileno"):
            return self.original_stream.fileno()
        raise OSError("Stream has no fileno")

    @property
    def encoding(self):
        if self.original_stream and hasattr(self.original_stream, "encoding"):
            return self.original_stream.encoding
        return "utf-8"

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def __getattr__(self, name):
        if self.original_stream:
            return getattr(self.original_stream, name)
        raise AttributeError(f"'PrintTeeStream' has no attribute '{name}'")


def setup_logging(level: int = logging.INFO, tee_stdout: bool = True):
    """
    Initialize rotating file handlers and console logging.
    Optionally tees sys.stdout and sys.stderr to capture all print() logs.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers on reload
    if not root_logger.handlers:
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

        # 1. Main rotating log file (10 MB, keep 5 backups)
        file_handler = RotatingFileHandler(
            str(LOG_FILE),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # 2. Error log file (warnings & errors only)
        err_handler = RotatingFileHandler(
            str(ERROR_LOG_FILE),
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        err_handler.setLevel(logging.WARNING)
        err_handler.setFormatter(formatter)
        root_logger.addHandler(err_handler)

        # 3. Console handler (safe for windowless GUI mode)
        if sys.stdout is not None:
            try:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(level)
                console_handler.setFormatter(formatter)
                root_logger.addHandler(console_handler)
            except Exception:
                pass

    # Tee sys.stdout and sys.stderr if requested, not already teed, and not running as daemon
    is_daemon = os.environ.get("LUGA_DAEMON_MODE") == "1"
    if tee_stdout and not is_daemon:
        if not isinstance(sys.stdout, PrintTeeStream):
            sys.stdout = PrintTeeStream(sys.stdout, LOG_FILE, is_err=False)
        if not isinstance(sys.stderr, PrintTeeStream):
            sys.stderr = PrintTeeStream(sys.stderr, LOG_FILE, is_err=True)

    logger = logging.getLogger("LugaAssist")
    logger.info("=" * 60)
    logger.info(f"Luga Assist Logger khởi động. File log: {LOG_FILE}")
    logger.info("=" * 60)
    return logger


def get_logger(name: str = "LugaAssist") -> logging.Logger:
    """Get named logger."""
    return logging.getLogger(name)


def read_recent_logs(max_lines: int = 150) -> List[str]:
    """Read the last N lines from the log file for debugging."""
    if not LOG_FILE.exists():
        return ["(Chưa có file log)"]
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return lines[-max_lines:] if len(lines) > max_lines else lines
    except Exception as e:
        return [f"Lỗi khi đọc file log: {e}"]


def clear_logs() -> bool:
    """Clear current log files."""
    try:
        if LOG_FILE.exists():
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("")
        if ERROR_LOG_FILE.exists():
            with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
                f.write("")
        return True
    except Exception:
        return False
