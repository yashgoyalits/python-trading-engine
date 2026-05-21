import asyncio
from src.logger import log
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ORDERS
from src.trade_store import ITradeStore
from src.infrastructure.trade_csv_logger import TradeCSVLogger


class OrderMonitor:
    def __init__(
        self,
        shm: ShmStore,
        trades: ITradeStore,
        trailing_event: asyncio.Event,
        csv_logger: TradeCSVLogger,
        strategy_id: str,
    ):
        self._shm            = shm
        self._trades         = trades
        self._trailing_event = trailing_event
        self._csv            = csv_logger
        self._sid            = strategy_id

    # ── main loop ─────────────────────────────────────────────

    async def run(self):
        ctrl           = self._shm.order_ctrl[0]
        last_read_widx = int(ctrl['widx'])

        try:
            while True:
                await asyncio.sleep(0.001)

                while last_read_widx != int(ctrl['widx']):
                    while True:
                        s1 = int(ctrl['seq'])
                        if s1 & 1:
                            await asyncio.sleep(0)
                            continue
                        slot = self._shm.orders[last_read_widx]
                        s2   = int(ctrl['seq'])
                        if s1 == s2:
                            break

                    await self._process_order(slot)
                    last_read_widx = (last_read_widx + 1) % MAX_ORDERS

        except asyncio.CancelledError:
            log.info(f"[{self._sid}] OrderMonitor: cancelled")

    # ── order filtering ───────────────────────────────────────

    async def _process_order(self, slot):
        order_id  = slot['order_id'].tobytes().rstrip(b'\x00').decode()
        parent_id = slot['parent_id'].tobytes().rstrip(b'\x00').decode()

        trade = self._trades.get_active()
        if trade is None:
            return

        trade_id = trade['order_id'].tobytes().rstrip(b'\x00').decode()

        if order_id == trade_id or parent_id == trade_id:
            await self._handle(slot, trade, trade_id)

    # ── order handling ────────────────────────────────────────

    async def _handle(self, slot, trade, trade_id: str):
        status     = int(slot['status'])
        order_type = int(slot['order_type'])
        order_id   = slot['order_id'].tobytes().rstrip(b'\x00').decode()
        parent_id  = slot['parent_id'].tobytes().rstrip(b'\x00').decode()

        # ── parent order ──────────────────────────────────────
        if order_id == trade_id:
            if status == 2:
                qty          = int(slot['qty'])
                traded_price = float(slot['traded_price'])
                symbol       = slot['symbol'].tobytes().rstrip(b'\x00').decode()
                log.info(f"[{self._sid}] Parent filled | {order_id}")
                self._trades.update(trade_id, symbol=symbol, qty=qty, entry_price=traded_price)
                self._trades.update(trade_id, trailing_levels=self._calc_trailing(traded_price))
                self._trailing_event.set()
            return

        # ── child orders ──────────────────────────────────────
        if parent_id == trade_id:
            if status == 6 and order_type == 4:
                stop_price = float(slot['stop_price'])
                if order_id != trade['stop_order_id'].tobytes().rstrip(b'\x00').decode():
                    log.info(f"[{self._sid}] Child SL update")
                    self._trades.update(trade_id, stop_order_id=order_id, stop_price=stop_price)

            if status == 6 and order_type == 1:
                limit_price = float(slot['limit_price'])
                if order_id != trade['target_order_id'].tobytes().rstrip(b'\x00').decode():
                    log.info(f"[{self._sid}] Child TP update")
                    self._trades.update(trade_id, target_order_id=order_id, target_price=limit_price)

            if status == 2:
                log.info(f"[{self._sid}] Child filled | {order_id}")
                self._csv.log_close(trade)
                self._trades.close_trade(trade_id)

            if status == 1:
                log.info(f"[{self._sid}] Child cancelled | {order_id}")

    # ── trailing calc ─────────────────────────────────────────

    def _calc_trailing(self, entry: float) -> list[dict]:
        return [
            {"threshold": entry + 1.0, "new_stop": entry + 0.5,  "hit": False},
            {"threshold": entry + 2.0, "new_stop": entry + 1.0,  "hit": False},
            {"threshold": entry + 3.0, "new_stop": entry + 2.0,  "hit": False},
        ]
