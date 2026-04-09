from src.core.dtypes import MAX_SYMBOLS


class SymbolRegistry:
    def __init__(self):
        self._map: dict[str, int] = {}

    def register(self, symbol: str) -> int:
        assert len(self._map) < MAX_SYMBOLS, "MAX_SYMBOLS reached"
        if symbol not in self._map:
            self._map[symbol] = len(self._map)
        return self._map[symbol]

    def idx(self, symbol: str) -> int:
        return self._map[symbol]

    def get(self, symbol: str) -> int | None:
        return self._map.get(symbol)

    def all(self) -> dict[str, int]:
        return dict(self._map)
