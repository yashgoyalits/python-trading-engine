# src/strategies/strategy_one/entry_detection.py
import asyncio
from src.logger import log
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_CANDLE_HISTORY, TF_30S, TF_1M, TF_3M
from src.strategies.strategy_one.logic import EntryLogic

_TF_SEQ = {
    TF_30S: 'c30s_seq',
    TF_1M:  'c1m_seq',
    TF_3M:  'c3m_seq',
}
_TF_WIDX = {
    TF_30S: 'c30s_widx',
    TF_1M:  'c1m_widx',
    TF_3M:  'c3m_widx',
}
_TF_CANDLES = {
    TF_30S: 'candles_30s',
    TF_1M:  'candles_1m',
    TF_3M:  'candles_3m',
}


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

        entry_tf         = config['entry_tf']
        self._seq_field  = _TF_SEQ[entry_tf]
        self._widx_field = _TF_WIDX[entry_tf]
        self._candle_arr = _TF_CANDLES[entry_tf]

    async def run(self) -> int:
        """
        Signal milne tak block karo.
        Return: 1 (buy) ya -1 (sell)
        """
        base     = self._sym_idx * MAX_CANDLE_HISTORY
        ctrl     = self._shm.ctrl[self._sym_idx]
        last_seq = int(ctrl[self._seq_field])

        while True:
            await asyncio.sleep(0.001)

            cur_seq = int(ctrl[self._seq_field])
            if cur_seq == last_seq:
                continue

            last_seq = cur_seq

            widx   = int(ctrl[self._widx_field])
            cidx   = (widx - 1) % MAX_CANDLE_HISTORY
            candle = getattr(self._shm, self._candle_arr)[base + cidx]

            side = self._logic.check_entry(candle)
            if side is not None:
                log.info(f"[{self._sid}] Entry signal | side={side}")
                return side