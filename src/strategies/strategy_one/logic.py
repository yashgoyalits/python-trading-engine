class StrategyLogicManager:
    def check_entry(self, candle) -> bool:
        """candle is a direct numpy row view."""
        o = float(candle['open'])
        h = float(candle['high'])
        l = float(candle['low'])
        c = float(candle['close'])

        if h == l:
            return False
        body_pct = abs(c - o) / (h - l) * 100
        if body_pct < 5:
            return False
        return c != o
