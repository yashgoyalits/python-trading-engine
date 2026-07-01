# src/engine.py
import asyncio
from dotenv import load_dotenv
from src.config import load
from src.logger import log, stop_log_listener
from src.core.shm_store import ShmStore
from src.symbol_manager.symbol_manager import SymbolManager
from src.broker.fyers.data_broker import FyersDataBroker
from src.broker.fyers.order_broker import FyersOrderBroker
from src.executor.live_executor import LiveExecutor
from src.managers.candle_builder import CandleBuilder
from src.managers.atm_tracker import ATMTracker
from src.trade_manager import TradeRegistry
from src.strategies.strategy_one.handler import StrategyHandler


class EngineStartupError(Exception):
    """Connect ya Health-Check phase fail — Bootstrap se alag, yeh runtime infra failure hai."""
    pass


class Engine:

    def __init__(self) -> None:
        # None defaults — _init() beech mein fail ho jaye to bhi _stop() safely chal sake
        self._shm          = None
        self._sym_manager       = None
        self._data_broker   = None
        self._order_broker  = None
        self._executor      = None
        self._candles       = None
        self._atm_tracker   = None
        self._strategy      = None

    # ── Phase 1: Init ─────────────────────────────────────────
    def _init(self) -> None:
        load_dotenv()  # loading .env variables
        cfg = load()
        tfs = cfg['timeframes']   # [30, 60, 180] — ek jagah se sab

        self._shm     = ShmStore(timeframes=tfs, create=True)
        self._sym_manager = SymbolManager(timeframes=tfs)

        self._data_broker  = FyersDataBroker(self._shm, self._sym_manager)
        self._order_broker = FyersOrderBroker(self._shm)
        self._executor     = LiveExecutor()

        self._sym_manager.set_broker(self._data_broker)

        for scfg in cfg['strategies']:
            self._sym_manager.add(scfg['entry_symbol'])

        registry = TradeRegistry(self._shm)

        self._candles = CandleBuilder(self._shm, self._sym_manager)

        scfg = cfg['strategies'][0]
        self._strategy = StrategyHandler(
            shm=self._shm,
            symbols=self._sym_manager,
            trades=registry.register(scfg['id']),
            executor=self._executor,
            config=scfg,
        )

        self._atm_tracker = ATMTracker(
            shm     = self._shm,
            symbols = self._sym_manager,
            sym_idx = self._sym_manager.idx("NSE:NIFTY50-INDEX"),
        )

        log.info("Engine: init done")

    # ── Phase 2: Connect ──────────────────────────────────────
    # Sirf connection attempts fire karo — readiness verify yahan nahi.
    async def _connect(self) -> None:
        loop = asyncio.get_running_loop()

        self._data_broker.connect(loop)     # non-blocking, thread spawn karke return
        self._order_broker.connect(loop)    # non-blocking, thread spawn karke return
        await self._executor.connect()      # blocking — already self-retrying (REST_CONNECT_POLICY)
                                             # + self-verifying (/profile check ke saath)

        log.info("Engine: connect phase done — connection attempts fired")

    # ── Phase 3: Health Check ─────────────────────────────────
    # Verify karo ki Connect ne jo start kiya woh actually live hua ya nahi.
    async def _health_check(self) -> None:
        try:
            await asyncio.gather(
                self._wait_ready(self._data_broker.is_connected,  "DataBroker"),
                self._wait_ready(self._order_broker.is_connected, "OrderBroker"),
            )
        except TimeoutError as e:
            raise EngineStartupError(str(e)) from e

        if not self._executor.is_connected():
            raise EngineStartupError("Executor not connected after connect phase")

        log.info(f"Engine: health check passed — Executor ready: {self._executor.is_connected()}")

    # ── Phase 4: Run ──────────────────────────────────────────
    async def _run(self) -> None:
        log.info("Engine: running")

        strategy_task = asyncio.create_task(
            self._strategy.run(), name="strategy"
        )
        support_tasks = [
            asyncio.create_task(self._candles.run(),     name="candles"),
            asyncio.create_task(self._atm_tracker.run(), name="atm_tracker"),
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

    # ── Phase 5: Stop ─────────────────────────────────────────
    # Har step guarded — _init() ya _connect() beech mein fail ho jaye to bhi
    # yeh None-check ke saath safely chalega, AttributeError nahi degā.
    async def _stop(self) -> None:
        log.info("Engine: stopping")

        if self._data_broker is not None:
            self._data_broker.disconnect()

        if self._order_broker is not None:
            self._order_broker.disconnect()

        if self._executor is not None:
            await self._executor.disconnect()

        if self._shm is not None:
            self._shm.cleanup()

        log.info("Engine: stopped")
        stop_log_listener()

    # ── Entrypoint ────────────────────────────────────────────
    # Sab phases EK try block ke andar — kisi bhi phase mein fail ho,
    # _stop() guaranteed chalega (SHM cleanup, broker disconnect).
    async def run(self) -> None:
        try:
            self._init()
            await self._connect()
            await self._health_check()
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