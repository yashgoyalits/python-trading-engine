# src/strategies/strategy_one/order_monitor.py
import asyncio
from src.logger import log
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ORDERS
from src.trade_manager import IActiveTradeManager


class OrderMonitor:
    def __init__(
        self,
        shm: ShmStore,
        trades: IActiveTradeManager,
        trailing_event: asyncio.Event,
        trade_closed_event: asyncio.Event,
        strategy_id: str,
        trailing_cfg: list[dict],
    ):
        self._shm                = shm
        self._trades             = trades
        self._trailing_event     = trailing_event
        self._trade_closed_event = trade_closed_event   # handler ko signal
        self._sid                = strategy_id
        self._trailing_cfg       = trailing_cfg

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
                self._trade_closed_event.set()   # ← handler ko signal — trade done

            if status == 1:
                log.info(f"[{self._sid}] Child cancelled | {order_id}")

    # ── trailing calc — config se ─────────────────────────────

    def _calc_trailing(self, entry: float) -> list[dict]:
        return [
            {
                "threshold": entry + lvl['threshold_offset'],
                "new_stop":  entry + lvl['new_stop_offset'],
                "hit":       False,
            }
            for lvl in self._trailing_cfg
        ]