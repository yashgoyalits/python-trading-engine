from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ACTIVE_TRADES
from src.trade_store.active_trade import ActiveTradesManager
from src.trade_store.protocol import ITradeStore


class TradeRegistry:
    def __init__(self, shm: ShmStore, total_slots: int = MAX_ACTIVE_TRADES):
        self._shm        = shm
        self._total      = total_slots
        self._next_slot  = 0
        self._stores: dict[str, ITradeStore] = {}

    def register(self, strategy_id: str) -> ITradeStore:
        slot_count = 1
        assert strategy_id not in self._stores, \
            f"{strategy_id} already registered"
        assert self._next_slot + slot_count <= self._total, \
            f"Slots exhausted: need {slot_count}, left {self._total - self._next_slot}"

        store = ActiveTradesManager(
            shm=self._shm,
            strategy_id=strategy_id,
            slot_start=self._next_slot,
            slot_count=slot_count,
        )
        self._next_slot += slot_count
        self._stores[strategy_id] = store
        return store

    def release(self, strategy_id: str) -> None:
        self._stores.pop(strategy_id, None)