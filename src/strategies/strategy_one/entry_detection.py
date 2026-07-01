# src/strategies/strategy_one/entry_detection.py
import asyncio
from src.logger import log
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_CANDLE_HISTORY
from src.strategies.strategy_one.logic import EntryLogic

class EntryDetectionLoop:
    def __init__(
        self,
        shm: ShmStore,
        sym_idx: int,
        strategy_id: str,
        config: dict,
    ):
        self._shm     = shm
        self._sym_idx = sym_idx
        self._sid     = strategy_id
        self._logic   = EntryLogic()

        entry_tf      = config['entry_tf']
        self._entry_tf = entry_tf

        # Precompute both — neither changes after init
        # tf_idx: integer slot index into ctrl sub-arrays
        self._tf_idx = shm.tf_map[entry_tf]
        self._base   = sym_idx * MAX_CANDLE_HISTORY

    async def run(self) -> tuple[int, float]:
        """
        Signal milne tak block karo.
        Return: (side, close_price) — side: 1 (buy) ya -1 (sell)
        """
        tf      = self._entry_tf
        tf_idx  = self._tf_idx          # precomputed int — no lookup in loop
        base    = self._base            # precomputed int — no lookup in loop
        ctrl    = self._shm.ctrl[self._sym_idx]
        candles = self._shm.candles[tf]

        # Integer index — direct byte offset into sub-array
        last_seq = int(ctrl['tf_seq'][tf_idx])

        while True:
            await asyncio.sleep(0.001)

            cur_seq = int(ctrl['tf_seq'][tf_idx])
            if cur_seq == last_seq:
                continue

            last_seq = cur_seq

            widx   = int(ctrl['tf_widx'][tf_idx])
            cidx   = (widx - 1) % MAX_CANDLE_HISTORY
            candle = candles[base + cidx]

            side = self._logic.check_entry(candle)
            if side is not None:
                return side, float(candle['close'])