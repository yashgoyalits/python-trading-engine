import csv
import os
import time
from pathlib import Path

_FIELDS = (
    "trade_no", "strategy_id", "symbol", "side", "qty",
    "entry_price", "stop_price", "target_price",
    "order_id", "stop_order_id", "target_order_id",
    "closed_at",
)

# Project root = is file se 3 levels upar (infrastructure → src → root)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CSV_DIR      = _PROJECT_ROOT / "csv"


class TradeCSVLogger:
    def __init__(self, filename: str = "trades.csv"):
        _CSV_DIR.mkdir(exist_ok=True)
        self._path = _CSV_DIR / filename
        if not self._path.exists():
            with open(self._path, "w", newline="") as f:
                csv.writer(f).writerow(_FIELDS)

    def log_close(self, trade_view) -> None:
        row = (
            int(trade_view["trade_no"]),
            trade_view["strategy_id"].tobytes().rstrip(b"\x00").decode(),
            trade_view["symbol"].tobytes().rstrip(b"\x00").decode(),
            int(trade_view["side"]),
            int(trade_view["qty"]),
            float(trade_view["entry_price"]),
            float(trade_view["stop_price"]),
            float(trade_view["target_price"]),
            trade_view["order_id"].tobytes().rstrip(b"\x00").decode(),
            trade_view["stop_order_id"].tobytes().rstrip(b"\x00").decode(),
            trade_view["target_order_id"].tobytes().rstrip(b"\x00").decode(),
            time.time(),
        )
        with open(self._path, "a", newline="") as f:
            csv.writer(f).writerow(row)