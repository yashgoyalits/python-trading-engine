import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_CANDLE_HISTORY, TF_30S
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger
from src.trade_store import ITradeStore
from src.executor.base_executor import BaseExecutor 
from src.strategies.strategy_one.trailing import TrailingManager
from src.strategies.strategy_one.logic import StrategyLogicManager


class StrategyHandler:
    def __init__(
        self,
        shm: ShmStore,
        symbols: SymbolRegistry,
        trades: ITradeStore,
        executor: BaseExecutor,
        logger: ShmLogger,
        strategy_id: str,
        sym_name: str,
        trailing_event: asyncio.Event,
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

        self._trailing_event = trailing_event
        self._trailing       = TrailingManager(trades, executor, logger)
        
        self._last_candle_seq = 0
        self._last_tick_seq   = 0

        self._tasks: list[asyncio.Task] = []

    # ── lifecycle ──────────────────────────────────────────────

    async def run(self):
        self._tasks = [
            asyncio.create_task(self._candle_loop(), name="candle"),
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
        base     = self._sym_idx * MAX_CANDLE_HISTORY
        ctrl     = self._shm.ctrl[self._sym_idx]
        last_seq = int(ctrl['c30s_seq'])          # pehla seq capture — skip initial fire

        try:
            while True:
                await asyncio.sleep(0.001)

                cur_seq = int(ctrl['c30s_seq'])
                if cur_seq == last_seq:
                    continue

                last_seq = cur_seq

                widx   = int(ctrl['c30s_widx'])
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
        else: 
            self._log.error(f"[{self._sid}] Order placement failed: {res}")