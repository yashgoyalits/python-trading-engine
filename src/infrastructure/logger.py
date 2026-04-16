import logging
from logging.handlers import RotatingFileHandler


def _setup_file_logger(log_path: str = "trading.log") -> logging.Logger:
    logger = logging.getLogger("trading")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    return logger


class ShmLogger:
    INFO    = 20
    WARNING = 30
    ERROR   = 40
    DEBUG   = 10

    def __init__(self, log_path: str = "trading.log"):
        self._logger = _setup_file_logger(log_path)

    def _write(self, level: int, msg: str):
        label = {10: "DEBUG", 20: "INFO", 30: "WARN", 40: "ERROR"}.get(level, "LOG")
        print(f"[{label}] {msg}")
        self._logger.log(level, msg)

    def debug(self, msg: str):   self._write(self.DEBUG,   msg)
    def info(self, msg: str):    self._write(self.INFO,    msg)
    def warning(self, msg: str): self._write(self.WARNING, msg)
    def error(self, msg: str):   self._write(self.ERROR,   msg)