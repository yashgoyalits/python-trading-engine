# src/engine.py
import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import TF_30S, TF_1M, TF_3M
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger, stop_log_listener
from src.infrastructure.trade_csv_logger import TradeCSVLogger
from src.broker.fyers.data_broker import FyersDataBroker
from src.broker.fyers.order_broker import FyersOrderBroker
from src.executor.live_executor import LiveExecutor
from src.managers.candle_builder import CandleBuilder
from src.trade_store import TradeRegistry
from src.strategies.strategy_one.handler import StrategyHandler


class Engine:

    # ── Phase 1: Init — sync, no IO ───────────────────────────
    def _init(self) -> None:
        self._shm    = ShmStore(create=True)
        self._syms   = SymbolRegistry()
        self._logger = ShmLogger()

        self._syms.register("NSE:NIFTY50-INDEX")

        self._data_broker  = FyersDataBroker(self._shm, self._syms, self._logger)
        self._order_broker = FyersOrderBroker(self._shm, self._logger)
        self._executor     = LiveExecutor()

        registry             = TradeRegistry(self._shm)
        active_trade_manager = registry.register("STRATEGY_ONE")

        trailing_event = asyncio.Event()
        csv_logger     = TradeCSVLogger("trades.csv")

        self._candles = CandleBuilder(
            self._shm, self._syms,
            watched={"NSE:NIFTY50-INDEX": [TF_30S, TF_1M, TF_3M]},
            logger=self._logger,
        )
        self._strategy = StrategyHandler(
            shm=self._shm,
            symbols=self._syms,
            trades=active_trade_manager,
            executor=self._executor,
            logger=self._logger,
            strategy_id="STRATEGY_ONE",
            sym_name="NSE:NIFTY50-INDEX",
            trailing_event=trailing_event,
            csv_logger=csv_logger,
            max_trades=1,
        )
        self._logger.info("Engine: init done")

    # ── Phase 2: Start — IO, connect + wait ready ─────────────
    async def _start(self) -> None:
        loop = asyncio.get_running_loop()

        self._data_broker.connect(loop)
        self._order_broker.connect(loop)
        await self._executor.connect()

        await self._wait_ready(self._data_broker.is_connected,  "DataBroker")
        await self._wait_ready(self._order_broker.is_connected, "OrderBroker")

        self._logger.info(f"Executor ready: {self._executor.is_connected()}")

        self._data_broker.subscribe(["NSE:NIFTY50-INDEX"])
        self._logger.info("Engine: start done — all connections live")

    # ── Phase 3: Run — strategy primary, candles subordinate ──
    async def _run(self) -> None:
        self._logger.info("Engine: running")

        strategy_task = asyncio.create_task(
            self._strategy.run(), name="strategy"
        )
        support_tasks = [
            asyncio.create_task(self._candles.run(), name="candles"),
        ]

        try:
            # Block here — strategy returns only when max_trades exhausted
            await strategy_task
            self._logger.info("Engine: strategy complete")

        except asyncio.CancelledError:
            # External interrupt (e.g. KeyboardInterrupt → asyncio cancels main task)
            self._logger.info("Engine: cancelled externally")
            strategy_task.cancel()
            await asyncio.gather(strategy_task, return_exceptions=True)
            raise

        finally:
            # Support tasks are always torn down after strategy exits (any reason)
            for t in support_tasks:
                t.cancel()
            await asyncio.gather(*support_tasks, return_exceptions=True)
            self._logger.info("Engine: support tasks stopped")

    # ── Phase 4: Stop — ordered teardown ──────────────────────
    async def _stop(self) -> None:
        self._logger.info("Engine: stopping")
        self._data_broker.disconnect()
        self._order_broker.disconnect()
        await self._executor.disconnect()
        self._shm.cleanup()
        self._logger.info("Engine: stopped")
        stop_log_listener()   # flush + join log thread — must be last

    # ── Entrypoint ────────────────────────────────────────────
    async def run(self) -> None:
        self._init()
        await self._start()
        try:
            await self._run()
        finally:
            await self._stop()

    # ── Helpers ───────────────────────────────────────────────
    @staticmethod
    async def _wait_ready(
        check_fn,
        name: str,
        poll: float = 0.1,
        timeout: float = 30.0,
    ) -> None:
        elapsed = 0.0
        while not check_fn():
            await asyncio.sleep(poll)
            elapsed += poll
            if elapsed >= timeout:
                raise TimeoutError(f"{name} did not connect within {timeout}s")
