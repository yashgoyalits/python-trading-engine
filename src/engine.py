import asyncio
import uvloop
from src.core.shm_store import ShmStore
from src.core.dtypes import TF_30S, TF_1M, TF_3M
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger
from src.infrastructure.trade_csv_logger import TradeCSVLogger
from src.broker.fyers.data_broker import FyersDataBroker
from src.broker.fyers.order_broker import FyersOrderBroker
from src.executor.live_executor import LiveExecutor
from src.managers.candle_builder import CandleBuilder
from src.managers.active_trades import ActiveTradesManager
from src.managers.order_feed_manager import OrderFeedManager
from src.strategies.strategy_one.handler import StrategyHandler


async def main():
    shm    = ShmStore(create=True)
    syms   = SymbolRegistry()
    logger = ShmLogger()

    syms.register("NSE:NIFTY50-INDEX")

    loop = asyncio.get_running_loop()

    # ── 1. Brokers ────────────────────────────────────────────
    data_broker  = FyersDataBroker(shm, syms, logger)
    order_broker = FyersOrderBroker(shm, logger)

    # ── 2. Executor ───────────────────────────────────────────
    executor = LiveExecutor()

    # ── 3. Connect ────────────────────────────────────────────
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

    # ── 6. Shared objects ─────────────────────────────────────
    trades         = ActiveTradesManager(shm, "STRATEGY_ONE")
    trailing_event = asyncio.Event()
    csv_logger     = TradeCSVLogger("trades.csv")

    # ── 7. Managers ───────────────────────────────────────────
    candles = CandleBuilder(
        shm, syms,
        watched={"NSE:NIFTY50-INDEX": [TF_30S, TF_1M, TF_3M]},
        logger=logger,
    )

    order_feed = OrderFeedManager(
        shm=shm,
        trades=trades,
        logger=logger,
        trailing_event=trailing_event,
        csv_logger=csv_logger,
        strategy_id="STRATEGY_ONE",
    )

    strategy = StrategyHandler(
        shm=shm,
        symbols=syms,
        trades=trades,
        executor=executor,
        logger=logger,
        strategy_id="STRATEGY_ONE",
        sym_name="NSE:NIFTY50-INDEX",
        trailing_event=trailing_event,
        max_trades=1,
    )

    logger.info("Engine started")

    try:
        await asyncio.gather(
            candles.run(),
            strategy.run(),
            order_feed.run(),
        )
    finally:
        data_broker.disconnect()
        order_broker.disconnect()
        await executor.disconnect()
        shm.cleanup()
        stop_log_listener()
        logger.info("Engine stopped")