import time
import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_LOGS


class ShmLogger:
    """Write-anywhere (thread or async). Readers poll log_ctrl seq."""

    INFO    = 20
    WARNING = 30
    ERROR   = 40
    DEBUG   = 10

    def __init__(self, shm: ShmStore):
        self._shm = shm

    def _write(self, level: int, msg: str):
        ctrl = self._shm.log_ctrl[0]
        widx = int(ctrl['widx'])
        slot = self._shm.logs[widx]
        slot['seq']       = int(ctrl['seq']) + 1
        slot['timestamp'] = time.time()
        slot['level']     = level
        slot['message']   = msg.encode()[:255]
        ctrl['widx']      = (widx + 1) % MAX_LOGS
        ctrl['seq']      += 1
        # Also print immediately for dev visibility
        print(f"[{'DEBUG' if level==10 else 'INFO' if level==20 else 'WARN' if level==30 else 'ERROR'}] {msg}")

    def debug(self, msg: str):   self._write(self.DEBUG,   msg)
    def info(self, msg: str):    self._write(self.INFO,    msg)
    def warning(self, msg: str): self._write(self.WARNING, msg)
    def error(self, msg: str):   self._write(self.ERROR,   msg)
