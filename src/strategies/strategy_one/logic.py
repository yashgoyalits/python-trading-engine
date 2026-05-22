# src/strategies/strategy_one/logic.py

class EntryLogic:
    def check_entry(self, candle) -> int | None:
        """
        Return: 1 (buy), -1 (sell), None (no signal)
        """
        o = float(candle['open'])
        h = float(candle['high'])
        l = float(candle['low'])
        c = float(candle['close'])

        if h == l:
            return None

        body_pct = abs(c - o) / (h - l) * 100
        if body_pct < 5:
            return None

        if c == o:
            return None

        return 1 if c > o else -1