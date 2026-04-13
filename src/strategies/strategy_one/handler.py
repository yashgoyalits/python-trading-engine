import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import (
    MAX_CANDLE_HISTORY, MAX_ORDERS,
    TF_30S,
)
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger
from src.managers.active_trades import ActiveTradesManager
from src.broker.fyers.order_placement import FyersOrderPlacement
from src.strategies.strategy_one.trailing import TrailingManager
from src.strategies.strategy_one.logic import StrategyLogicManager


class StrategyHandler:
    def __init__(
        self,
        shm: ShmStore,
        symbols: SymbolRegistry,
        trades: ActiveTradesManager,
        placement: FyersOrderPlacement,
        logger: ShmLogger,
        strategy_id: str,
        sym_name: str,
        max_trades: int = 1,
    ):
        self._shm      = shm
        self._sym_idx  = symbols.idx(sym_name)
        self._trades   = trades
        self._place    = placement
        self._log      = logger
        self._sid      = strategy_id
        self._max      = max_trades
        self._done     = 0
        self._trailing = TrailingManager(trades, placement, logger)
        self._logic    = StrategyLogicManager()

        self._last_candle_seq = 0
        self._last_tick_seq   = 0
        self._last_order_seq  = 0

        self._tasks: list[asyncio.Task] = []

    # ── lifecycle ──────────────────────────────────────────────

    async def run(self):
        self._tasks = [
            asyncio.create_task(self._candle_loop(), name="candle"),
            asyncio.create_task(self._tick_loop(),   name="tick"),
            asyncio.create_task(self._order_loop(),  name="order"),
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._log.info(f"[{self._sid}] All tasks done: {[t.get_name() for t in self._tasks]}")

    def _stop_all(self):
        for t in self._tasks:
            if not t.done():
                t.cancel()

    # ── candle loop ────────────────────────────────────────────

    async def _candle_loop(self):
        base  = self._sym_idx * MAX_CANDLE_HISTORY
        first = True
        try:
            while True:
                cur = int(self._shm.ctrl[self._sym_idx]['c30s_seq'])
                if cur != self._last_candle_seq:
                    if first:
                        first = False
                        self._last_candle_seq = cur
                        await asyncio.sleep(0)
                        continue

                    self._last_candle_seq = cur
                    widx   = int(self._shm.ctrl[self._sym_idx]['c30s_widx'])
                    cidx   = (widx - 1) % MAX_CANDLE_HISTORY
                    candle = self._shm.candles_30s[base + cidx]

                    trade = self._trades.get_active()

                    # Active Trade Check
                    if trade is None:
                        # Max Trade Check
                        if self._done >= self._max:
                            self._log.info(
                                f"[{self._sid}] Max trade limit reached: {self._done}. Stopping all loops."
                            )
                            self._stop_all()
                            return

                        if self._logic.check_entry(candle):
                            await self._enter()
                    # else: trade chal rahi hai, candle loop kuch nahi karta — tick/order loop handle karenge

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            self._log.info(f"[{self._sid}] candle_loop cancelled.")

    # ── tick loop ──────────────────────────────────────────────

    async def _tick_loop(self):
        tick_base = self._sym_idx * 200
        try:
            while True:
                cur = int(self._shm.ctrl[self._sym_idx]['tick_seq'])
                if cur != self._last_tick_seq:
                    self._last_tick_seq = cur
                    widx = int(self._shm.ctrl[self._sym_idx]['tick_widx'])
                    tick = self._shm.ticks[tick_base + (widx - 1) % 200]

                    trade = self._trades.get_active()
                    if trade is not None:
                        await self._trailing.check(tick, trade)

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            self._log.info(f"[{self._sid}] tick_loop cancelled.")

    # ── order loop ─────────────────────────────────────────────

    async def _order_loop(self):
        last_processed_seq = 0
        try:
            while True:
                ctrl_seq = int(self._shm.order_ctrl[0]['seq'])
                if ctrl_seq != self._last_order_seq:
                    widx = int(self._shm.order_ctrl[0]['widx'])
                    for i in range(MAX_ORDERS):
                        slot = self._shm.orders[i]
                        s    = int(slot['seq'])
                        if s > last_processed_seq:
                            await self._process_order(slot)
                            last_processed_seq = max(last_processed_seq, s)
                    self._last_order_seq = ctrl_seq

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            self._log.info(f"[{self._sid}] order_loop cancelled.")

    # ── helpers ────────────────────────────────────────────────

    async def _enter(self):
        res = await self._place.place_order(
            symbol="NSE:IDEA-EQ", qty=1, order_type=2,
            side=1, stop_loss=0.5, take_profit=2.0,
        )
        if res.get('code') == 1101:
            self._done += 1
            self._trades.add_trade(self._done, res.get("id", ""))
            self._log.info(f"[{self._sid}] Order placed {res.get('id')}")

    async def _process_order(self, order):
        trade = self._trades.get_active()
        if trade is None:
            return

        oid      = order['order_id'].decode().rstrip('\x00')
        pid      = order['parent_id'].decode().rstrip('\x00')
        status   = int(order['status'])
        trade_id = trade['order_id'].decode().rstrip('\x00')

        self._log.info(f"Order UPDATES: {order}")

        # Parent 
        if oid == trade_id:
            # Transit
            if status == 4:
                self._log.info(f"[{self._sid}] Parent transit: {oid}")
            # Filled
            if status == 2:
                self._log.info(f"[{self._sid}] Parent filled: {oid}")
                self._trades.update(
                    trade_id,
                    qty=int(order['qty']),
                    entry_price=float(order['limit_price']),
                )

        # Child
        if pid == trade_id:
            # Transit
            if status == 4:
                self._log.info(f"[{self._sid}] Child transit: {oid}")
            # Pending
            if status == 6:
                self._trades.update(trade_id,
                    stop_order_id=oid,
                    stop_price=float(order['stop_price']),
                )
            if status == 6:
                self._trades.update(trade_id,
                    target_order_id=oid,
                    target_price=float(order['limit_price']),
                )
            # Filled
            if status == 2:
                self._log.info(
                    f"[{self._sid}] Child filled, closing trade: {oid} | ParentID: {trade_id}"
                )
                self._trades.close_trade(trade_id)
            # Cancelled
            if status == 1:
                self._log.info(
                    f"[{self._sid}] Order cancelled ID: {oid} | ParentID: {trade_id}"
                )