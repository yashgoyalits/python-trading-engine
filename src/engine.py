# src/engine.py
import asyncio
from src.logger import log, stop_log_listener
from src.core.shm_store import ShmStore
from src.core.dtypes import TF_30S, TF_1M, TF_3M
from src.infrastructure.symbol_manager import SymbolManager
from src.broker.fyers.data_broker import FyersDataBroker
from src.broker.fyers.order_broker import FyersOrderBroker
from src.executor.live_executor import LiveExecutor
from src.managers.candle_builder import CandleBuilder
from src.trade_manager import TradeRegistry
from src.strategies.strategy_one.handler import StrategyHandler


class Engine:

    # ── Phase 1: Init — sync, no IO ───────────────────────────
    def _init(self) -> None:
        self._shm     = ShmStore(create=True)

        # ── SymbolManager pehle (broker ke bina) ──────────────
        self._symbols = SymbolManager()

        # ── Brokers — SymbolManager ref lo data_broker ke liye
        self._data_broker  = FyersDataBroker(self._shm, self._symbols)
        self._order_broker = FyersOrderBroker(self._shm)
        self._executor     = LiveExecutor()

        # ── Ab broker inject karo ─────────────────────────────
        self._symbols.set_broker(self._data_broker)

        # ── Symbols register karo — broker auto-subscribe karega _start() mein
        # (set_broker ke baad add() call hoga toh subscribe bhi hoga)
        self._symbols.add("NSE:NIFTY50-INDEX", [TF_30S, TF_1M, TF_3M])

        # ── Registry + strategy ───────────────────────────────
        registry             = TradeRegistry(self._shm)
        active_trade_manager = registry.register("STRATEGY_ONE")

        # ── CandleBuilder — sirf manager chahiye, watched dict nahi
        self._candles = CandleBuilder(self._shm, self._symbols)

        self._strategy = StrategyHandler(
            shm=self._shm,
            symbols=self._symbols,
            trades=active_trade_manager,
            executor=self._executor,
            strategy_id="STRATEGY_ONE",
            sym_name="NSE:NIFTY50-INDEX",
            max_trades=1,
        )
        log.info("Engine: init done")

    # ── Phase 2: Start — IO, connect + wait ready ─────────────
    async def _start(self) -> None:
        loop = asyncio.get_running_loop()

        self._data_broker.connect(loop)
        self._order_broker.connect(loop)
        await self._executor.connect()

        await self._wait_ready(self._data_broker.is_connected,  "DataBroker")
        await self._wait_ready(self._order_broker.is_connected, "OrderBroker")

        log.info(f"Executor ready: {self._executor.is_connected()}")

        # Broker connected hai — ab sab registered symbols subscribe karo
        # (add() ne pehle set_broker ke baad subscribe kiya tha, but agar
        #  broker tab connected nahi tha toh yahan explicit subscribe safe hai)
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