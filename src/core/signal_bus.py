# src/core/signal_bus.py
import asyncio
from enum import IntEnum
from typing import Callable

class Signal(IntEnum):
    CANDLE_30S_CLOSE = 0
    CANDLE_1M_CLOSE  = 1
    CANDLE_3M_CLOSE  = 2

_MAX_SIGNALS = len(Signal)

class SignalBus:
    __slots__ = ('_subs',)

    def __init__(self):
        # Fixed list at startup — no runtime allocation
        self._subs: list[list[Callable]] = [[] for _ in range(_MAX_SIGNALS)]

    def subscribe(self, signal: Signal, cb: Callable) -> None:
        self._subs[signal].append(cb)

    def fire(self, signal: Signal) -> None:
        if asyncio.get_running_loop() is None:
            raise RuntimeError("fire outside loop")

        for cb in self._subs[signal]:
            cb()