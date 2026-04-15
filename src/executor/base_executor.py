from abc import ABC, abstractmethod


class BaseExecutor(ABC):

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        qty: int,
        order_type: int,
        side: int,
        stop_loss: float,
        take_profit: float,
    ) -> dict: ...

    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        order_type: int,
        limit_price: float,
        stop_price: float,
        qty: int,
    ) -> dict: ...