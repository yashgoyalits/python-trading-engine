from src.executor.base_executor import BaseExecutor
from src.broker.fyers.order_placement import FyersOrderPlacement


class LiveExecutor(BaseExecutor):

    def __init__(self):
        self._broker = FyersOrderPlacement()

    # ── lifecycle ──────────────────────────────────────────────

    async def connect(self) -> None:
        await self._broker.connect()

    def is_connected(self) -> bool:
        return self._broker.is_connected()

    async def disconnect(self) -> None:
        await self._broker.disconnect()

    # ── order ops ─────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        qty: int,
        order_type: int,
        side: int,
        stop_loss: float,
        take_profit: float,
    ) -> dict:
        return await self._broker.place_order(
            symbol=symbol,
            qty=qty,
            order_type=order_type,
            side=side,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    async def modify_order(
        self,
        order_id: str,
        order_type: int,
        limit_price: float,
        stop_price: float,
        qty: int,
    ) -> dict:
        return await self._broker.modify_order(
            order_id=order_id,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            qty=qty,
        )