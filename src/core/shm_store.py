from multiprocessing.shared_memory import SharedMemory
import numpy as np
from src.core.dtypes import *


class ShmStore:
    def __init__(self, create: bool = True):
        self._shms: dict[str, SharedMemory] = {}
        self._create = create

        self.ticks      = self._alloc("ticks",      MAX_SYMBOLS * MAX_TICKS_PER_SYMBOL, TICK_DTYPE)
        self.candles_30s = self._alloc("c30s",       MAX_SYMBOLS * MAX_CANDLE_HISTORY,   CANDLE_DTYPE)
        self.candles_1m  = self._alloc("c1m",        MAX_SYMBOLS * MAX_CANDLE_HISTORY,   CANDLE_DTYPE)
        self.candles_3m  = self._alloc("c3m",        MAX_SYMBOLS * MAX_CANDLE_HISTORY,   CANDLE_DTYPE)
        self.ctrl        = self._alloc("ctrl",        MAX_SYMBOLS,                        CTRL_DTYPE)
        self.orders      = self._alloc("orders",      MAX_ORDERS,                         ORDER_DTYPE)
        self.order_ctrl  = self._alloc("order_ctrl",  1,                                  ORDER_CTRL_DTYPE)
        self.trades      = self._alloc("trades",      MAX_ACTIVE_TRADES,                  TRADE_DTYPE)
        self.logs        = self._alloc("logs",        MAX_LOGS,                           LOG_DTYPE)
        self.log_ctrl    = self._alloc("log_ctrl",    1,                                  LOG_CTRL_DTYPE)

    def _alloc(self, name: str, count: int, dtype: np.dtype) -> np.ndarray:
        size = count * dtype.itemsize
        try:
            shm = SharedMemory(name=name, create=self._create, size=size)
        except FileExistsError:
            shm = SharedMemory(name=name, create=False, size=size)
        self._shms[name] = shm
        arr = np.ndarray(count, dtype=dtype, buffer=shm.buf)
        if self._create:
            arr[:] = 0
        return arr

    def cleanup(self):
        for shm in self._shms.values():
            shm.close()
            if self._create:
                try:
                    shm.unlink()
                except Exception:
                    pass
