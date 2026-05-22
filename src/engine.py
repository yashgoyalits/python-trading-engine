# src/engine.py
import asyncio
from src.config import load
from src.logger import log, stop_log_listener
from src.core.shm_store import ShmStore
from src.infrastructure.symbol_manager import SymbolManager
from src.broker.fyers.data_broker import FyersDataBroker
from src.broker.fyers.order_broker import FyersOrderBroker
from src.executor.live_executor import LiveExecutor
from src.managers.candle_builder import CandleBuilder
from src.trade_manager import TradeRegistry
from src.strategies.strategy_one.handler import StrategyHandler


class Engine:

    # ── Phase 1: Init ─────────────────────────────────────────
    def _init(self) -> None:
        cfg = load()
        tfs = cfg['timeframes']   # [30, 60, 180] — ek jagah se sab

        self._shm     = ShmStore(timeframes=tfs, create=True)
        self._symbols = SymbolManager()

        self._data_broker  = FyersDataBroker(self._shm, self._symbols)
        self._order_broker = FyersOrderBroker(self._shm)
        self._executor     = LiveExecutor()

        self._symbols.set_broker(self._data_broker)

        for scfg in cfg['strategies']:
            for sym in scfg['symbols']:
                self._symbols.add(sym, tfs)

        registry = TradeRegistry(self._shm)

        self._candles = CandleBuilder(self._shm, self._symbols)

        scfg = cfg['strategies'][0]
        self._strategy = StrategyHandler(
            shm=self._shm,
            symbols=self._symbols,
            trades=registry.register(scfg['id']),
            executor=self._executor,
            config=scfg,
        )

        log.info("Engine: init done")

    # ── Phase 2: Start ────────────────────────────────────────
    async def _start(self) -> None:
        loop = asyncio.get_running_loop()

        self._data_broker.connect(loop)
        self._order_broker.connect(loop)
        await self._executor.connect()

        await self._wait_ready(self._data_broker.is_connected,  "DataBroker")
        await self._wait_ready(self._order_broker.is_connected, "OrderBroker")

        log.info(f"Executor ready: {self._executor.is_connected()}")

        for sym in self._symbols.all_symbols():
            self._data_broker.subscribe([sym])

        log.info("Engine: start done — all connections live")

    # ── Phase 3: Run ──────────────────────────────────────────
    async def _run(self) -> None:
        log.info("Engine: running")

        strategy_task = asyncio.create_task(
            self._strategy.run(), name="strategy"
        )
        support_tasks = [
            asyncio.create_task(self._candles.run(), name="candles"),
        ]

        try:
            await strategy_task
            log.info("Engine: strategy complete")

        except asyncio.CancelledError:
            log.info("Engine: cancelled externally")
            strategy_task.cancel()
            await asyncio.gather(strategy_task, return_exceptions=True)
            raise

        finally:
            for t in support_tasks:
                t.cancel()
            await asyncio.gather(*support_tasks, return_exceptions=True)
            log.info("Engine: support tasks stopped")

    # ── Phase 4: Stop ─────────────────────────────────────────
    async def _stop(self) -> None:
        log.info("Engine: stopping")
        self._data_broker.disconnect()
        self._order_broker.disconnect()
        await self._executor.disconnect()
        self._shm.cleanup()
        log.info("Engine: stopped")
        stop_log_listener()

    # ── Entrypoint ────────────────────────────────────────────
    async def run(self) -> None:
        self._init()
        await self._start()
        try:
            await self._run()
        finally:
            await self._stop()

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