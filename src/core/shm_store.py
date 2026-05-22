import mmap
import os
import numpy as np
from pathlib import Path
from src.core.dtypes import *

SHM_DIR = Path("/tmp/trading_shm")


class ShmStore:
    def __init__(self, timeframes: list[int], create: bool = True):
        self._mmaps:  dict[str, mmap.mmap] = {}
        self._create  = create
        SHM_DIR.mkdir(exist_ok=True)

        # ctrl — pehle jaisa ek hi array, bas dtype ab dynamic hai
        ctrl_dtype      = make_ctrl_dtype(timeframes)
        self.ctrl       = self._alloc("ctrl",       MAX_SYMBOLS,                        ctrl_dtype)
        self.ticks      = self._alloc("ticks",      MAX_SYMBOLS * MAX_TICKS_PER_SYMBOL, TICK_DTYPE)
        self.orders     = self._alloc("orders",     MAX_ORDERS,                         ORDER_DTYPE)
        self.order_ctrl = self._alloc("order_ctrl", 1,                                  ORDER_CTRL_DTYPE)
        self.trades     = self._alloc("trades",     MAX_ACTIVE_TRADES,                  TRADE_DTYPE)

        # candles — tf value hi key hai, named arrays nahi
        self.candles: dict[int, np.ndarray] = {
            tf: self._alloc(f"c{tf}", MAX_SYMBOLS * MAX_CANDLE_HISTORY, CANDLE_DTYPE)
            for tf in timeframes
        }

    def _alloc(self, name: str, count: int, dtype: np.dtype) -> np.ndarray:
        size = count * dtype.itemsize
        path = SHM_DIR / name

        if self._create:
            fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_TRUNC, 0o600)
            os.ftruncate(fd, size)
        else:
            fd = os.open(str(path), os.O_RDWR)

        mm = mmap.mmap(fd, size, access=mmap.ACCESS_WRITE)
        os.close(fd)

        self._mmaps[name] = mm
        arr = np.ndarray(count, dtype=dtype, buffer=mm)

        if self._create:
            arr[:] = 0

        return arr

    def cleanup(self):
        for name, mm in self._mmaps.items():
            mm.close()
            if self._create:
                path = SHM_DIR / name
                try:
                    path.unlink()
                except Exception:
                    pass