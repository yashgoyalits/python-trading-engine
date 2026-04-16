import time
import logging
from logging.handlers import RotatingFileHandler
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_LOGS

_LEVEL_MAP = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR"}

def _setup_file_logger(log_path: str = "trading.log") -> logging.Logger:
    logger = logging.getLogger("trading")
    if logger.handlers:
        return logger  # already setup hai

    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,               # trading.log, trading.log.1 ... .5
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

    def __init__(self, shm: ShmStore, log_path: str = "trading.log"):
        self._shm    = shm
        self._logger = _setup_file_logger(log_path)

    def _write(self, level: int, msg: str):
        ctrl = self._shm.log_ctrl[0]

        # relaxed index (may overwrite → acceptable for logs)
        widx = int(ctrl['widx'])
        ctrl['widx'] = (widx + 1) % MAX_LOGS

        slot = self._shm.logs[widx]

        # ── SEQLOCK START ──
        slot['seq'] += 1   # odd → writer active

        slot['timestamp'] = time.time()
        slot['level']     = level
        slot['message']   = msg.encode()[:255]

        slot['seq'] += 1   # even → write complete
        # ── SEQLOCK END ──

        # Console (optional but slow)
        print(f"[{'DEBUG' if level==10 else 'INFO' if level==20 else 'WARN' if level==30 else 'ERROR'}] {msg}")

        # File logging (safe)
        self._logger.log(level, msg)

    def debug(self, msg: str):   self._write(self.DEBUG,   msg)
    def info(self, msg: str):    self._write(self.INFO,    msg)
    def warning(self, msg: str): self._write(self.WARNING, msg)
    def error(self, msg: str):   self._write(self.ERROR,   msg)