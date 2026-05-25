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
        self._shm      = shm
        self._sym_idx  = sym_idx
        self._sid      = strategy_id
        self._logic    = EntryLogic()
        self._entry_tf = config['entry_tf']

    async def run(self) -> int:
        """
        Signal milne tak block karo.
        Return: 1 (buy) ya -1 (sell)
        """
        tf       = self._entry_tf
        base     = self._sym_idx * MAX_CANDLE_HISTORY
        ctrl     = self._shm.ctrl[self._sym_idx]   # pehle jaisa ek hi ctrl
        candles  = self._shm.candles[tf]
        last_seq = int(ctrl[f'c{tf}_seq'])

        while True:
            await asyncio.sleep(0.001)

            cur_seq = int(ctrl[f'c{tf}_seq'])
            if cur_seq == last_seq:
                continue

            last_seq = cur_seq

            widx   = int(ctrl[f'c{tf}_widx'])
            cidx   = (widx - 1) % MAX_CANDLE_HISTORY
            candle = candles[base + cidx]

            side = self._logic.check_entry(candle)
            if side is not None:
                log.info(candle)
                log.info(f"[{self._sid}] Entry signal | side={side}")
                return side, candle['close']