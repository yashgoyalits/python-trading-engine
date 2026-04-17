import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import (
    MAX_CANDLE_HISTORY, MAX_ORDERS,
    TF_30S,
)
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger
from src.managers.active_trades import ActiveTradesManager
from src.executor.base_executor import BaseExecutor 
from src.strategies.strategy_one.trailing import TrailingManager
from src.strategies.strategy_one.logic import StrategyLogicManager
from src.infrastructure.trade_csv_logger import TradeCSVLogger


class StrategyHandler:
    def __init__(
        self,
        shm: ShmStore,
        symbols: SymbolRegistry,
        trades: ActiveTradesManager,
        executor: BaseExecutor,
        logger: ShmLogger,
        strategy_id: str,
        sym_name: str,
        max_trades: int = 1,
    ):
        self._shm      = shm
        self._sym_idx  = symbols.idx(sym_name)
        self._trades   = trades
        self._executor = executor
        self._log      = logger
        self._sid      = strategy_id
        self._max      = max_trades
        self._done     = 0
        self._logic    = StrategyLogicManager()
        self._csv      = TradeCSVLogger("trades.csv")

        self._candle_event = asyncio.Event()

        # ── Trailing: event se handoff control hoga ───────────
        self._trailing_event = asyncio.Event()
        self._trailing       = TrailingManager(trades, executor, logger)

        self._last_candle_seq = 0
        self._last_tick_seq   = 0
        self._last_order_seq  = 0

        self._tasks: list[asyncio.Task] = []

    # ── lifecycle ──────────────────────────────────────────────

    async def run(self):
        self._tasks = [
            asyncio.create_task(self._candle_loop(), name="candle"),
            asyncio.create_task(self._order_loop(),  name="order"),
            asyncio.create_task(
                self._trailing.run(self._sym_idx, self._shm, self._trailing_event),
                name=f"{self._sid}_trailing",
            ),
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
                await self._candle_event.wait()
                self._candle_event.clear()

                if first:
                    first = False
                    continue

                widx   = int(self._shm.ctrl[self._sym_idx]['c30s_widx'])
                cidx   = (widx - 1) % MAX_CANDLE_HISTORY
                candle = self._shm.candles_30s[base + cidx]

                trade = self._trades.get_active()

                if trade is None:
                    if self._done >= self._max:
                        self._log.info(
                            f"[{self._sid}] Max trade limit reached: {self._done}. Stopping all loops."
                        )
                        self._stop_all()
                        return

                    if self._logic.check_entry(candle):
                        await self._enter()

        except asyncio.CancelledError:
            self._log.info(f"[{self._sid}] candle_loop cancelled.")

    # ── order loop ─────────────────────────────────────────────

    async def _order_loop(self):
        last_read_widx = 0
        try:
            while True:
                ctrl_seq = int(self._shm.order_ctrl[0]['seq'])
                if ctrl_seq != self._last_order_seq:
                    widx = int(self._shm.order_ctrl[0]['widx'])
                    while last_read_widx != widx:
                        order = self._shm.orders[last_read_widx].copy()
                        await self._process_order(order)
                        last_read_widx = (last_read_widx + 1) % MAX_ORDERS
                    self._last_order_seq = ctrl_seq

                await asyncio.sleep(0)

        except asyncio.CancelledError:
            self._log.info(f"[{self._sid}] order_loop cancelled.")

    # ── helpers ────────────────────────────────────────────────

    async def _enter(self):
        res = await self._executor.place_order(
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
        order_type = int(order['order_type'])
        trade_id = trade['order_id'].decode().rstrip('\x00')

        # ── Parent ─────────────────────────────────────────────────
        if oid == trade_id:
            if status == 2:
                self._log.info(f"[{self._sid}] | Parent filled | Order ID: {oid}")

                # basic trade info SHM mein likho
                self._trades.update(
                    trade_id,
                    symbol=order['symbol'].decode().rstrip('\x00'),
                    qty=int(order['qty']),
                    entry_price=float(order['traded_price']),
                )

                # trailing levels calculate karke SHM mein likho
                levels = self._calc_trailing(float(order['traded_price']))
                self._log.info(f"[{self._sid}] Trailing levels: {levels}")
                self._trades.update(trade_id, trailing_levels=levels)

                # SHM ready hai — ab trailing task ko jagao
                self._trailing_event.set()

            return  

        # ── Child ──────────────────────────────────────────────────
        if pid == trade_id:
            if status == 6 and order_type == 4:  # STOP LOSS
                if oid != trade['stop_order_id'].tobytes().rstrip(b'\x00').decode():
                    self._log.info(f"[{self._sid}] | Child stop loss update")
                    self._trades.update(trade_id,
                        stop_order_id=oid,
                        stop_price=float(order['stop_price']),
                    )
            if status == 6 and order_type == 1:  # TAKE PROFIT
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