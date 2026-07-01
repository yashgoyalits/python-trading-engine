# src/symbol_manager/subscription_manager.py
from __future__ import annotations
from src.symbol_manager.symbol_manager import SymbolManager

class SubscriptionManager:

    def __init__(self, symbols: SymbolManager, broker):
        self._symbols = symbols
        self._broker  = broker

    def add(self, symbol: str) -> int:
        idx = self._symbols.add(symbol)
        if self._broker.is_connected():
            self._broker.subscribe([symbol])
        return idx

    def remove(self, symbol: str) -> None:
        if self._symbols.get(symbol) is None:
            return
        self._symbols.remove(symbol)
        if self._broker.is_connected():
            self._broker.unsubscribe([symbol])

    def ensure(self, symbol: str) -> int:
        idx = self._symbols.get(symbol)
        if idx is not None:
            return idx
        return self.add(symbol)