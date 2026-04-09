import asyncio
import uvloop
from src.core.shm_store import ShmStore
from src.core.dtypes import TF_30S, TF_1M, TF_3M
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger
from src.broker.fyers.data_broker import FyersDataBroker
from src.broker.fyers.order_broker import FyersOrderBroker
from src.managers.candle_builder import CandleBuilder
from src.managers.active_trades import ActiveTradesManager
from src.managers.order_placement_manager import FyersOrderPlacement
from src.strategies.strategy_one.handler import StrategyHandler


async def main():
    shm    = ShmStore(create=True)
    syms   = SymbolRegistry()
    logger = ShmLogger(shm)

    # Register symbols
    syms.register("NSE:NIFTY50-INDEX")

    loop = asyncio.get_running_loop()

    data_broker  = FyersDataBroker(shm, syms, logger)
    order_broker = FyersOrderBroker(shm, logger)

    data_broker.connect(loop)
    order_broker.connect(loop)

    # Wait for connections
    while not data_broker.is_connected():
        await asyncio.sleep(0.1)
    logger.info("Data WS ready")

    data_broker.subscribe(["NSE:NIFTY50-INDEX"])

    candles = CandleBuilder(
        shm, syms,
        watched={"NSE:NIFTY50-INDEX": [TF_30S, TF_1M, TF_3M]},
        logger=logger,
    )

    trades    = ActiveTradesManager(shm, "STRATEGY_ONE")
    placement = FyersOrderPlacement()
    strategy  = StrategyHandler(
        shm, syms, trades, placement, logger,
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
        shm.cleanup()
        logger.info("Engine stopped")


if __name__ == "__main__":
    uvloop.install()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")
