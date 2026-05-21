import queue
import logging
import logging.handlers
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_log_queue: queue.SimpleQueue = queue.SimpleQueue()
_listener: logging.handlers.QueueListener | None = None

# Project root = infrastructure → src → root (3 levels up)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR      = _PROJECT_ROOT / "logs"


def _default_log_path() -> str:
    _LOG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(_LOG_DIR / f"trading_{timestamp}.log")


def _setup_file_logger(log_path: str | None = None) -> logging.Logger:
    global _listener

    logger = logging.getLogger("trading")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    resolved_path = log_path or _default_log_path()

    file_h = RotatingFileHandler(
        resolved_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
    )
    file_h.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    console_h = logging.StreamHandler()
    console_h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    _listener = logging.handlers.QueueListener(
        _log_queue, file_h, console_h,
        respect_handler_level=True,
    )
    _listener.start()

    logger.addHandler(logging.handlers.QueueHandler(_log_queue))
    return logger


def stop_log_listener():
    if _listener:
        _listener.stop()


class ShmLogger:
    INFO    = 20
    WARNING = 30
    ERROR   = 40
    DEBUG   = 10

    def __init__(self, log_path: str | None = None):
        self._logger = _setup_file_logger(log_path)

    def _write(self, level: int, msg: str):
        self._logger.log(level, msg)

    def debug(self, msg: str):   self._write(self.DEBUG,   msg)
    def info(self, msg: str):    self._write(self.INFO,    msg)
    def warning(self, msg: str): self._write(self.WARNING, msg)
    def error(self, msg: str):   self._write(self.ERROR,   msg)

log = ShmLogger()