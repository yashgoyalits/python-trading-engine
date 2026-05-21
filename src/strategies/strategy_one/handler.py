import asyncio
from src.logger import log
from src.core.shm_store import ShmStore
from src.infrastructure.shm_symbols import SymbolRegistry
from src.trade_store import ITradeStore
from src.executor.base_executor import BaseExecutor
from src.strategies.strategy_one.entry_detection import EntryDetectionLoop
from src.strategies.strategy_one.order_monitor import OrderMonitor
from src.strategies.strategy_one.trailing import TrailingManager


class StrategyHandler:
    def __init__(
        self,
        shm: ShmStore,
        symbols: SymbolRegistry,
        trades: ITradeStore,
        executor: BaseExecutor,
        strategy_id: str,
        sym_name: str,
        max_trades: int = 1,
    ):
        self._shm      = shm
        self._sym_idx  = symbols.idx(sym_name)
        self._trades   = trades
        self._sid      = strategy_id
        self._max      = max_trades
        self._done     = 0

        self._trailing_event = asyncio.Event()

        # ── sub-components ─────────────────────────────────────
        self._candle_loop = EntryDetectionLoop(
            shm=shm,
            sym_idx=self._sym_idx,
            trades=trades,
            executor=executor,
            strategy_id=strategy_id,
            on_trade_placed=self._on_trade_placed,
            is_max_reached=self.is_max_reached,
        )
        self._order_monitor = OrderMonitor(
            shm=shm,
            trades=trades,
            trailing_event=self._trailing_event,
            strategy_id=strategy_id,
        )
        self._trailing = TrailingManager(trades, executor)

    # ── lifecycle ──────────────────────────────────────────────

    async def run(self):
        candle_task = asyncio.create_task(
            self._candle_loop.run(), name=f"{self._sid}_candle"
        )
        support_tasks = [
            asyncio.create_task(
                self._order_monitor.run(), name=f"{self._sid}_order_monitor"
            ),
            asyncio.create_task(
                self._trailing.run(self._sym_idx, self._shm, self._trailing_event),
                name=f"{self._sid}_trailing",
            ),
        ]

        try:
            # Block here — candle_loop returns only when max_trades exhausted
            await candle_task
            log.info(f"[{self._sid}] Candle loop complete")

        except asyncio.CancelledError:
            log.info(f"[{self._sid}] Cancelled externally")
            candle_task.cancel()
            await asyncio.gather(candle_task, return_exceptions=True)
            raise

        finally:
            # Support tasks always torn down after candle loop exits
            for t in support_tasks:
                t.cancel()
            await asyncio.gather(*support_tasks, return_exceptions=True)
            log.info(f"[{self._sid}] Support tasks stopped")

    # ── trade count management ─────────────────────────────────

    def _on_trade_placed(self, order_id: str):
        self._done += 1
        self._trades.add_trade(self._done, order_id)
        log.info(f"[{self._sid}] Order placed #{self._done} | {order_id}")

    def is_max_reached(self) -> bool:
        return self._done >= self._max
