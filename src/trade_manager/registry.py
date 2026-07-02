#src/trade_manager/registery.py
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ACTIVE_TRADES
from src.trade_manager.active_trade import ActiveTradeManager
from src.trade_manager.protocol import IActiveTradeManager

class TradeManagerFactory:
    def __init__(
        self,
        shm: ShmStore,
        total_slots: int = MAX_ACTIVE_TRADES,
    ):
        self._shm = shm
        self._next_slot = 0
        self._total_slots = total_slots

    def create(self, strategy_id: str) -> IActiveTradeManager:
        if self._next_slot >= self._total_slots:
            raise RuntimeError("No free trade slots available.")

        trade_mgr = ActiveTradeManager(
            shm=self._shm,
            strategy_id=strategy_id,
            slot_start=self._next_slot,
        )

        self._next_slot += 1
        return trade_mgr