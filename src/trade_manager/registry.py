from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ACTIVE_TRADES
from src.trade_manager.active_trade import ActiveTradeManager
from src.trade_manager.protocol import IActiveTradeManager


class TradeRegistry:
    def __init__(self, shm: ShmStore, total_slots: int = MAX_ACTIVE_TRADES):
        self._shm        = shm
        self._total      = total_slots
        self._next_slot  = 0
        self._stores: dict[str, IActiveTradeManager] = {}

    def register(self, strategy_id: str) -> IActiveTradeManager:
        store = ActiveTradeManager(
            shm=self._shm,
            strategy_id=strategy_id,
            slot_start=self._next_slot,
        )
        self._next_slot += 1
        self._stores[strategy_id] = store
        return store

    def all(self) -> list[IActiveTradeManager]:
        return list(self._stores.values())

    def release(self, strategy_id: str) -> None:
        self._stores.pop(strategy_id, None)