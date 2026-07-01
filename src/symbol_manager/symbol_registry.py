# src/symbol_manager/symbol_manager.py
from __future__ import annotations
from src.core.dtypes import MAX_SYMBOLS

class SymbolRegistry:

    def __init__(self, timeframes: list[int]):
        self._map:         dict[str, int]      = {}
        self._tfs:         dict[int, list[int]] = {}
        self._tfs_default: list[int]           = timeframes
        self._next_idx:    int                 = 0
        self._free:        list[int]           = []  # freed slots pool

        # tf_value → ctrl sub-array slot index, same as shm.tf_map
        self.tf_map: dict[int, int] = {
            tf: idx for idx, tf in enumerate(timeframes)
        }

    def add(self, symbol: str) -> int:
        if symbol not in self._map:
            # reuse freed slot, else allocate new
            if self._free:
                idx = self._free.pop()
            else:
                assert self._next_idx < MAX_SYMBOLS, "MAX_SYMBOLS limit hit"
                idx = self._next_idx
                self._next_idx += 1
            self._map[symbol] = idx

        idx = self._map[symbol]
        self._tfs[idx] = self._tfs_default

        return idx

    def remove(self, symbol: str) -> None:
        idx = self._map.pop(symbol, None)
        if idx is None:
            return

        self._tfs.pop(idx, None)
        self._free.append(idx)  # return slot to pool

    def idx(self, symbol: str) -> int:
        # strict — KeyError if not registered
        return self._map[symbol]

    def get(self, symbol: str) -> int | None:
        # safe — None if missing (used by data_broker._on_message)
        return self._map.get(symbol)

    def subscriptions(self) -> dict[int, list[int]]:
        # live snapshot: {sym_idx: [tf, ...]}
        return dict(self._tfs)

    def all_symbols(self) -> dict[str, int]:
        return dict(self._map)