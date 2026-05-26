import mmap
import os
import numpy as np
from pathlib import Path
from src.core.dtypes import (
    CTRL_DTYPE, TICK_DTYPE, CANDLE_DTYPE,
    ORDER_DTYPE, ORDER_CTRL_DTYPE, TRADE_DTYPE,
    MAX_SYMBOLS, MAX_TICKS_PER_SYMBOL, MAX_CANDLE_HISTORY,
    MAX_ORDERS, MAX_TF,
)

SHM_DIR = Path("/tmp/trading_shm")


class ShmStore:
    def __init__(self, timeframes: list[int], create: bool = True):
        assert len(timeframes) <= MAX_TF, (
            f"timeframes count {len(timeframes)} exceeds MAX_TF={MAX_TF}"
        )

        self._mmaps:  dict[str, mmap.mmap] = {}
        self._create  = create
        SHM_DIR.mkdir(exist_ok=True)

        # tf_map: tf_value → sub-array slot index
        # Built once at startup — O(1) int lookup in hot path
        # e.g. [30, 60, 180] → {30: 0, 60: 1, 180: 2}
        self.tf_map: dict[int, int] = {
            tf: idx for idx, tf in enumerate(timeframes)
        }

        # ctrl — fixed dtype, no dynamic field resolution at runtime
        self.ctrl       = self._alloc("ctrl",       MAX_SYMBOLS,                        CTRL_DTYPE)
        self.ticks      = self._alloc("ticks",      MAX_SYMBOLS * MAX_TICKS_PER_SYMBOL, TICK_DTYPE)
        self.orders     = self._alloc("orders",     MAX_ORDERS,                         ORDER_DTYPE)
        self.order_ctrl = self._alloc("order_ctrl", 1,                                  ORDER_CTRL_DTYPE)
        self.trades     = self._alloc("trades",     MAX_SYMBOLS,                        TRADE_DTYPE)

        # candles — keyed by tf value, same as before
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