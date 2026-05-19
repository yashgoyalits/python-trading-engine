import queue
import logging
import logging.handlers
from logging.handlers import RotatingFileHandler

_log_queue: queue.SimpleQueue = queue.SimpleQueue()  # SimpleQueue — Queue se faster, lock-free
_listener: logging.handlers.QueueListener | None = None


def _setup_file_logger(log_path: str = "trading.log") -> logging.Logger:
    global _listener

    logger = logging.getLogger("trading")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    file_h = RotatingFileHandler(
        log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
    )
    file_h.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    console_h = logging.StreamHandler()
    console_h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

    # Background thread — actual file write yahan hota hai
    _listener = logging.handlers.QueueListener(
        _log_queue, file_h, console_h,
        respect_handler_level=True,
    )
    _listener.start()

    # Main logger — sirf queue mein daalta hai
    logger.addHandler(logging.handlers.QueueHandler(_log_queue))
    return logger


def stop_log_listener():
    if _listener:
        _listener.stop()  # flush + join background thread


# ─── ShmLogger — bilkul same interface ──────────────────────
class ShmLogger:
    INFO    = 20
    WARNING = 30
    ERROR   = 40
    DEBUG   = 10

    def __init__(self, log_path: str = "trading.log"):
        self._logger = _setup_file_logger(log_path)

    def _write(self, level: int, msg: str):
        self._logger.log(level, msg)  # non-blocking ab — queue mein jaata hai

    def debug(self, msg: str):   self._write(self.DEBUG,   msg)
    def info(self, msg: str):    self._write(self.INFO,    msg)
    def warning(self, msg: str): self._write(self.WARNING, msg)
    def error(self, msg: str):   self._write(self.ERROR,   msg)