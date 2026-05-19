import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ORDERS
from src.managers.active_trades import ActiveTradesManager
from src.infrastructure.logger import ShmLogger
from src.infrastructure.trade_csv_logger import TradeCSVLogger


class OrderFeedManager:
    def __init__(
        self,
        shm: ShmStore,
        trades: ActiveTradesManager,
        logger: ShmLogger,
        trailing_event: asyncio.Event,
        csv_logger: TradeCSVLogger,
        strategy_id: str,
    ):
        self._shm            = shm
        self._trades         = trades
        self._log            = logger
        self._trailing_event = trailing_event
        self._csv            = csv_logger
        self._sid            = strategy_id

    async def run(self):
        ctrl           = self._shm.order_ctrl[0]
        last_read_widx = int(ctrl['widx'])

        try:
            while True:
                await asyncio.sleep(0.001)

                while last_read_widx != int(ctrl['widx']):
                    slot = self._shm.orders[last_read_widx]

                    while True:
                        s1 = int(ctrl['seq'])
                        if s1 & 1:
                            await asyncio.sleep(0)
                            continue
                        s2 = int(ctrl['seq'])
                        if s1 == s2:
                            break

                    await self._process_order(slot)
                    last_read_widx = (last_read_widx + 1) % MAX_ORDERS

        except asyncio.CancelledError:
            self._log.info("OrderFeedManager: feed loop cancelled")

    async def _process_order(self, order):
        trade = self._trades.get_active()
        if trade is None:
            return

        oid        = order['order_id'].decode().rstrip('\x00')
        pid        = order['parent_id'].decode().rstrip('\x00')
        status     = int(order['status'])
        order_type = int(order['order_type'])
        trade_id   = trade['order_id'].decode().rstrip('\x00')

        # ── Parent ────────────────────────────────────────────
        if oid == trade_id:
            if status == 2:
                self._log.info(f"[{self._sid}] | Parent filled | Order ID: {oid}")

                self._trades.update(
                    trade_id,
                    symbol=order['symbol'].decode().rstrip('\x00'),
                    qty=int(order['qty']),
                    entry_price=float(order['traded_price']),
                )

                levels = self._calc_trailing(float(order['traded_price']))
                self._log.info(f"[{self._sid}] Trailing levels: {levels}")
                self._trades.update(trade_id, trailing_levels=levels)

                self._trailing_event.set()
            return

        # ── Child ─────────────────────────────────────────────
        if pid == trade_id:
            if status == 6 and order_type == 4:
                if oid != trade['stop_order_id'].tobytes().rstrip(b'\x00').decode():
                    self._log.info(f"[{self._sid}] | Child stop loss update")
                    self._trades.update(trade_id,
                        stop_order_id=oid,
                        stop_price=float(order['stop_price']),
                    )

            if status == 6 and order_type == 1:
                if oid != trade['target_order_id'].tobytes().rstrip(b'\x00').decode():
                    self._log.info(f"[{self._sid}] | Child take profit update")
                    self._trades.update(trade_id,
                        target_order_id=oid,
                        target_price=float(order['limit_price']),
                    )

            if status == 2:
                self._log.info(
                    f"[{self._sid}] | Child filled | Order ID: {oid} | ParentID: {trade_id}"
                )
                self._csv.log_close(trade)
                self._trades.close_trade(trade_id)

            if status == 1:
                self._log.info(
                    f"[{self._sid}] | Child cancelled | Order ID: {oid} | ParentID: {trade_id}"
                )

    def _calc_trailing(self, entry: float) -> list[dict]:
        return [
            {"threshold": entry + 1.0, "new_stop": entry + 0.5,  "hit": False},
            {"threshold": entry + 2.0, "new_stop": entry + 1.0,  "hit": False},
            {"threshold": entry + 3.0, "new_stop": entry + 2.0,  "hit": False},
        ]