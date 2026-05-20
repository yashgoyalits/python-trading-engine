import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ORDERS
from src.trade_store import ITradeStore
from src.trade_store.registry import TradeRegistry
from src.infrastructure.logger import ShmLogger
from src.infrastructure.trade_csv_logger import TradeCSVLogger


class OrderFeedManager:
    def __init__(
        self,
        shm: ShmStore,
        registry: TradeRegistry,
        logger: ShmLogger,
        trailing_event: asyncio.Event,
        csv_logger: TradeCSVLogger,
    ):
        self._shm            = shm
        self._registry       = registry
        self._log            = logger
        self._trailing_event = trailing_event
        self._csv            = csv_logger

    
    async def run(self):
        ctrl           = self._shm.order_ctrl[0]
        last_read_widx = int(ctrl['widx'])

        try:
            while True:
                await asyncio.sleep(0.001)

                while last_read_widx != int(ctrl['widx']):
                    
                    # SEQLOCK pehle, slot read baad mein
                    while True:
                        s1 = int(ctrl['seq'])
                        if s1 & 1:
                            await asyncio.sleep(0)
                            continue

                        slot = self._shm.orders[last_read_widx]

                        # fields copy karo SHM se bahar
                        status       = int(slot['status'])
                        order_type   = int(slot['order_type'])
                        qty          = int(slot['qty'])
                        stop_price   = float(slot['stop_price'])
                        limit_price  = float(slot['limit_price'])
                        traded_price = float(slot['traded_price'])
                        order_id     = slot['order_id'].tobytes().rstrip(b'\x00').decode()
                        parent_id    = slot['parent_id'].tobytes().rstrip(b'\x00').decode()
                        symbol       = slot['symbol'].tobytes().rstrip(b'\x00').decode()

                        s2 = int(ctrl['seq'])
                        if s1 == s2:
                            break
                        await asyncio.sleep(0.001)

                    await self._process_order(
                        status, order_type, qty,
                        stop_price, limit_price, traded_price,
                        order_id, parent_id, symbol,
                    )
                    last_read_widx = (last_read_widx + 1) % MAX_ORDERS

        except asyncio.CancelledError:
            self._log.info("OrderFeedManager: feed loop cancelled")


    async def _process_order(
        self,
        status: int, order_type: int, qty: int,
        stop_price: float, limit_price: float, traded_price: float,
        order_id: str, parent_id: str, symbol: str,
    ):
        for store in self._registry.all():               # ← sab strategies loop
            trade = store.get_active()
            if trade is None:
                continue

            trade_id = trade['order_id'].tobytes().rstrip(b'\x00').decode()

            if order_id == trade_id or parent_id == trade_id:
                await self._handle(store, trade, trade_id,
                                   status, order_type, qty,
                                   stop_price, limit_price, traded_price,
                                   order_id, parent_id, symbol)
                return                                   # match mila — stop

    async def _handle(
        self,
        store: ITradeStore,
        trade,
        trade_id: str,
        status: int, order_type: int, qty: int,
        stop_price: float, limit_price: float, traded_price: float,
        order_id: str, parent_id: str, symbol: str,
    ):
        if order_id == trade_id:
            if status == 2:
                self._log.info(f"Parent filled | Order ID: {order_id}")
                store.update(trade_id, symbol=symbol, qty=qty, entry_price=traded_price)
                levels = self._calc_trailing(traded_price)
                store.update(trade_id, trailing_levels=levels)
                self._trailing_event.set()
            return

        if parent_id == trade_id:
            if status == 6 and order_type == 4:
                if order_id != trade['stop_order_id'].tobytes().rstrip(b'\x00').decode():
                    self._log.info(f"Child stop loss update")
                    store.update(trade_id, stop_order_id=order_id, stop_price=stop_price)

            if status == 6 and order_type == 1:
                if order_id != trade['target_order_id'].tobytes().rstrip(b'\x00').decode():
                    self._log.info(f"Child take profit update")
                    store.update(trade_id, target_order_id=order_id, target_price=limit_price)

            if status == 2:
                self._log.info(f"Child filled | Order ID: {order_id}")
                self._csv.log_close(trade)
                store.close_trade(trade_id)

            if status == 1:
                self._log.info(f"Child cancelled | Order ID: {order_id}")
    

    def _calc_trailing(self, entry: float) -> list[dict]:
        return [
            {"threshold": entry + 1.0, "new_stop": entry + 0.5,  "hit": False},
            {"threshold": entry + 2.0, "new_stop": entry + 1.0,  "hit": False},
            {"threshold": entry + 3.0, "new_stop": entry + 2.0,  "hit": False},
        ]