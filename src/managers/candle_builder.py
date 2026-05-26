# src/managers/candle_builder.py
import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TICKS_PER_SYMBOL, MAX_CANDLE_HISTORY
from src.infrastructure.symbol_manager import SymbolManager


class CandleBuilder:
    def __init__(self, shm: ShmStore, manager: SymbolManager):
        self._shm     = shm
        self._manager = manager
        # Precompute once — used in _process() hot path
        # tf_value → sub-array slot index, e.g. {30: 0, 60: 1, 180: 2}
        self._tf_map: dict[int, int] = shm.tf_map

    async def run(self):
        last_widx: dict[int, int | None] = {}

        while True:
            subscriptions = self._manager.subscriptions()

            for sym_idx, timeframes in subscriptions.items():

                if sym_idx not in last_widx:
                    last_widx[sym_idx] = None

                ctrl     = self._shm.ctrl[sym_idx]
                cur_widx = int(ctrl['tick_widx'])

                if last_widx[sym_idx] is None:
                    last_widx[sym_idx] = cur_widx
                    continue

                read_idx = last_widx[sym_idx]

                while read_idx != cur_widx:
                    slot = self._shm.ticks[sym_idx * MAX_TICKS_PER_SYMBOL + read_idx]

                    # ── SEQLOCK ───────────────────────────────
                    while True:
                        s1 = int(ctrl['tick_seq'])
                        if s1 & 1:
                            await asyncio.sleep(0)
                            continue

                        ts  = float(slot['timestamp'])
                        ltp = float(slot['ltp'])
                        vol = int(slot['volume'])

                        s2 = int(ctrl['tick_seq'])
                        if s1 == s2:
                            break

                        await asyncio.sleep(0.001)
                    # ──────────────────────────────────────────

                    for tf in timeframes:
                        self._process(sym_idx, tf, ts, ltp, vol)

                    read_idx = (read_idx + 1) % MAX_TICKS_PER_SYMBOL

                last_widx[sym_idx] = cur_widx

            await asyncio.sleep(0.001)

    def _process(self, sym_idx: int, tf: int, ts: float, ltp: float, vol: int):
        ctrl    = self._shm.ctrl[sym_idx]
        candles = self._shm.candles[tf]
        bucket  = int(ts // tf)
        base    = sym_idx * MAX_CANDLE_HISTORY

        # Integer index — direct byte offset, no string hash lookup
        tf_idx = self._tf_map[tf]
        widx   = int(ctrl['tf_widx'][tf_idx])
        last_b = int(ctrl['tf_bucket'][tf_idx])

        if last_b == 0:
            ctrl['tf_bucket'][tf_idx] = bucket
            self._open_candle(candles[base + widx], ts, ltp, vol)
            return

        if bucket != last_b:
            candles[base + widx]['seq'] += 1          # close current candle
            new_widx                    = (widx + 1) % MAX_CANDLE_HISTORY
            ctrl['tf_bucket'][tf_idx]   = bucket
            ctrl['tf_widx'][tf_idx]     = new_widx
            ctrl['tf_seq'][tf_idx]     += 1           # signal entry detection
            self._open_candle(candles[base + new_widx], ts, ltp, vol)
        else:
            c = candles[base + widx]
            if ltp > c['high']: c['high'] = ltp
            if ltp < c['low']:  c['low']  = ltp
            c['close']  = ltp
            c['volume'] += vol

    @staticmethod
    def _open_candle(slot, ts: float, ltp: float, vol: int):
        slot['open']       = ltp
        slot['high']       = ltp
        slot['low']        = ltp
        slot['close']      = ltp
        slot['volume']     = vol
        slot['start_time'] = ts
        slot['seq']        = 0