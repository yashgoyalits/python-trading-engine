import asyncio
import uvloop
from src.core.shm_store import ShmStore
from src.core.dtypes import TF_30S, TF_1M, TF_3M
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger
from src.broker.fyers.data_broker import FyersDataBroker
from src.broker.fyers.order_broker import FyersOrderBroker
from src.broker.fyers.order_placement import FyersOrderPlacement   # ← updated
from src.managers.candle_builder import CandleBuilder
from src.managers.active_trades import ActiveTradesManager
from src.strategies.strategy_one.handler import StrategyHandler


async def main():
    shm    = ShmStore(create=True)
    syms   = SymbolRegistry()
    logger = ShmLogger(shm)

    syms.register("NSE:NIFTY50-INDEX")

    loop = asyncio.get_running_loop()

    # ── 1. Init all three brokers ──────────────────────────────
    data_broker     = FyersDataBroker(shm, syms, logger)
    order_broker    = FyersOrderBroker(shm, logger)
    order_placement = FyersOrderPlacement()

    # ── 2. Connect all three together ─────────────────────────
    data_broker.connect(loop)
    order_broker.connect(loop)
    await order_placement.connect()          # TCP pool + TLS warmup

    # ── 3. Wait for WS connections ────────────────────────────
    while not data_broker.is_connected():
        await asyncio.sleep(0.1)
    logger.info("Data WS ready")

    while not order_broker.is_connected():
        await asyncio.sleep(0.1)
    logger.info("Order WS ready")

    logger.info(f"Order placement ready: {order_placement.is_connected()}")

    # ── 4. Subscribe ──────────────────────────────────────────
    data_broker.subscribe(["NSE:NIFTY50-INDEX"])

    # ── 5. Build managers / strategy ──────────────────────────
    candles = CandleBuilder(
        shm, syms,
        watched={"NSE:NIFTY50-INDEX": [TF_30S, TF_1M, TF_3M]},
        logger=logger,
    )

    trades   = ActiveTradesManager(shm, "STRATEGY_ONE")
    strategy = StrategyHandler(
        shm, syms, trades, order_placement, logger,
        strategy_id="STRATEGY_ONE",
        sym_name="NSE:NIFTY50-INDEX",
        max_trades=1,
    )

    logger.info("Engine started")

    try:
        await asyncio.gather(
            candles.run(),
            strategy.run(),
        )
    finally:
        data_broker.disconnect()
        order_broker.disconnect()
        await order_placement.disconnect()   # ← clean close
        shm.cleanup()
        logger.info("Engine stopped")


if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")