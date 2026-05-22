# src/infrastructure/symbol_manager.py
from __future__ import annotations
from src.core.dtypes import MAX_SYMBOLS


class SymbolManager:
    """
    Ek jagah sab kuch:
      - symbol → idx mapping
      - idx → timeframes mapping
      - broker subscribe / unsubscribe

    Broker ke saath circular dependency se bachne ke liye
    set_broker() alag se call karo (engine._init() mein).
    """

    def __init__(self):
        self._map: dict[str, int] = {}        # symbol → shm idx
        self._tfs: dict[int, list[int]] = {}  # idx    → timeframes
        self._next_idx = 0
        self._broker = None                   # set_broker() se milega

    # ── broker wire ───────────────────────────────────────────

    def set_broker(self, broker) -> None:
        """DataBroker ref inject karo after both are constructed."""
        self._broker = broker

    # ── public API ────────────────────────────────────────────

    def add(self, symbol: str, timeframes: list[int]) -> int:
        """
        Symbol register karo + broker ko subscribe karo.
        Agar symbol pehle se hai toh sirf timeframes update hote hain.
        Returns: shm idx
        """
        assert self._next_idx < MAX_SYMBOLS, "MAX_SYMBOLS limit hit"

        if symbol not in self._map:
            self._map[symbol] = self._next_idx
            self._next_idx += 1

        idx = self._map[symbol]
        self._tfs[idx] = list(timeframes)

        if self._broker is not None:
            self._broker.subscribe([symbol])

        return idx

    def remove(self, symbol: str) -> None:
        """
        Symbol unsubscribe karo + mapping hata do.
        Note: shm slot reuse nahi hota (simple design).
        """
        idx = self._map.pop(symbol, None)
        if idx is None:
            return

        self._tfs.pop(idx, None)

        if self._broker is not None:
            self._broker.unsubscribe([symbol])

    def idx(self, symbol: str) -> int:
        """Strict lookup — KeyError if not registered."""
        return self._map[symbol]

    def get(self, symbol: str) -> int | None:
        """Broker ke _on_message ke liye — None return karo if missing."""
        return self._map.get(symbol)

    def subscriptions(self) -> dict[int, list[int]]:
        """
        CandleBuilder.run() loop mein use karo.
        Returns live snapshot: { idx: [tf, ...], ... }
        """
        return dict(self._tfs)

    def all_symbols(self) -> dict[str, int]:
        return dict(self._map)