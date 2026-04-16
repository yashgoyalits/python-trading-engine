import asyncio
import uvloop
from src.core.shm_store import ShmStore
from src.core.dtypes import TF_30S, TF_1M, TF_3M
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger
from src.broker.fyers.data_broker import FyersDataBroker
from src.broker.fyers.order_broker import FyersOrderBroker
from src.executor.live_executor import LiveExecutor          # ← new
from src.managers.candle_builder import CandleBuilder
from src.managers.active_trades import ActiveTradesManager
from src.strategies.strategy_one.handler import StrategyHandler
from src.core.signal_bus import SignalBus, Signal


async def main():
    shm    = ShmStore(create=True)
    syms   = SymbolRegistry()
    logger = ShmLogger(shm)

    syms.register("NSE:NIFTY50-INDEX")

    loop = asyncio.get_running_loop()

    # ── 1. Brokers (transport layer) ──────────────────────────
    data_broker  = FyersDataBroker(shm, syms, logger)
    order_broker = FyersOrderBroker(shm, logger)

    # ── 2. Executor (strategy-facing layer) ───────────────────
    executor = LiveExecutor()

    # ── 3. Connect all ────────────────────────────────────────
    data_broker.connect(loop)
    order_broker.connect(loop)
    await executor.connect()

    # ── 4. Wait for WS ────────────────────────────────────────
    while not data_broker.is_connected():
        await asyncio.sleep(0.1)
    logger.info("Data WS ready")

    while not order_broker.is_connected():
        await asyncio.sleep(0.1)
    logger.info("Order WS ready")

    logger.info(f"Executor ready: {executor.is_connected()}")

    # ── 5. Subscribe ──────────────────────────────────────────
    data_broker.subscribe(["NSE:NIFTY50-INDEX"])

    # engine.py
    bus = SignalBus()

    # ── 6. Managers & strategy ────────────────────────────────
    candles = CandleBuilder(
        shm, syms,
        watched={"NSE:NIFTY50-INDEX": [TF_30S, TF_1M, TF_3M]},
        logger=logger,
        bus=bus,
    )

    trades   = ActiveTradesManager(shm, "STRATEGY_ONE")
    strategy = StrategyHandler(
        shm, syms, trades,
        executor=executor,              # ← BaseExecutor pass ho raha hai
        logger=logger,
        strategy_id="STRATEGY_ONE",
        sym_name="NSE:NIFTY50-INDEX",
        max_trades=1,
    )

    bus.subscribe(Signal.CANDLE_30S_CLOSE, strategy._candle_event.set)

    logger.info("Engine started")

    try:
        await asyncio.gather(
            candles.run(),
            strategy.run(),
        )
    finally:
        data_broker.disconnect()
        order_broker.disconnect()
        await executor.disconnect()
        shm.cleanup()
        logger.info("Engine stopped")
