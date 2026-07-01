# src/symbol_manager/subscription_manager.py
from __future__ import annotations
from src.symbol_manager.symbol_registry import SymbolRegistry

class SubscriptionManager:

    def __init__(self, sym_rgstry: SymbolRegistry, broker):
        self._sym_rgstry = sym_rgstry
        self._broker  = broker

    def add(self, symbol: str) -> int:
        idx = self._sym_rgstry.add(symbol)
        if self._broker.is_connected():
            self._broker.subscribe([symbol])
        return idx

    def remove(self, symbol: str) -> None:
        if self._sym_rgstry.get(symbol) is None:
            return
        self._sym_rgstry.remove(symbol)
        if self._broker.is_connected():
            self._broker.unsubscribe([symbol])

    def ensure(self, symbol: str) -> int:
        idx = self._sym_rgstry.get(symbol)
        if idx is not None:
            return idx
        return self.add(symbol)