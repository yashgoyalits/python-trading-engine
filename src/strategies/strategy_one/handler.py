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

        # Last-seen seq counters — no queue
        self._last_candle_seq = 0
        self._last_tick_seq   = 0
        self._last_order_seq  = 0

    async def run(self):
        await asyncio.gather(
            self._candle_loop(),
            self._tick_loop(),
            self._order_loop(),
        )

    # ── candle loop ────────────────────────────────────────────

    async def _candle_loop(self):
        base = self._sym_idx * MAX_CANDLE_HISTORY
        first = True
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
                # Latest closed candle is one slot before current write index
                cidx   = (widx - 1) % MAX_CANDLE_HISTORY
                candle = self._shm.candles_30s[base + cidx]  # direct view

                trade = self._trades.get_active()
                if trade is None and self._done < self._max:
                    if self._logic.check_entry(candle):
                        await self._enter()

            await asyncio.sleep(0)

    # ── tick loop ──────────────────────────────────────────────

    async def _tick_loop(self):
        tick_base = self._sym_idx * 200
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

    # ── order loop ─────────────────────────────────────────────

    async def _order_loop(self):
        last_processed_seq = 0
        while True:
            ctrl_seq = int(self._shm.order_ctrl[0]['seq'])
            if ctrl_seq != self._last_order_seq:
                # Process all new orders since last check
                widx = int(self._shm.order_ctrl[0]['widx'])
                for i in range(MAX_ORDERS):
                    slot = self._shm.orders[i]
                    s = int(slot['seq'])
                    if s > last_processed_seq:
                        await self._process_order(slot)
                        last_processed_seq = max(last_processed_seq, s)
                self._last_order_seq = ctrl_seq

            await asyncio.sleep(0)

    # ── helpers ────────────────────────────────────────────────

    async def _enter(self):
        res = await self._place.place_order(
            symbol="NSE:IDEA-EQ", qty=1, order_type=2,
            side=1, stop_loss=0.5, take_profit=2.0,
        )
        if res.get('code') == 1101:
            self._done += 1
            self._trades.add_trade(self._done, res.get("id", ""))
            self._log.info(f"Order placed {res.get('id')}")

    async def _process_order(self, order):
        trade = self._trades.get_active()
        if trade is None:
            return

        oid      = order['order_id'].decode().rstrip('\x00')
        pid      = order['parent_id'].decode().rstrip('\x00')
        status   = int(order['status'])
        otype    = int(order['order_type'])
        trade_id = trade['order_id'].decode().rstrip('\x00')

        if oid == trade_id and otype == 2 and status == 2:
            self._log.info(f"Parent filled: {oid}")
            self._trades.update(
                trade_id,
                qty=int(order['qty']),
                entry_price=float(order['limit_price']),
            )

        if pid == trade_id:
            if otype == 4 and status == 6:
                self._trades.update(trade_id,
                    stop_order_id=oid,
                    stop_price=float(order['stop_price']),
                )
            if otype == 1 and status == 6:
                self._trades.update(trade_id,
                    target_order_id=oid,
                    target_price=float(order['limit_price']),
                )
            if status == 2:
                self._log.info(f"Child filled, closing trade: {oid} | ParentID: {trade_id}")
                self._trades.close_trade(trade_id)

            if status == 1:
                self._log.info(f"Order cancelled ID: {oid} | ParentID: {trade_id}")
                
