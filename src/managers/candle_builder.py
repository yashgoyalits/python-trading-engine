import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import (
    MAX_SYMBOLS, MAX_TICKS_PER_SYMBOL, MAX_CANDLE_HISTORY,
    TF_30S, TF_1M, TF_3M,
)
from src.infrastructure.shm_symbols import SymbolRegistry
from src.infrastructure.logger import ShmLogger
from src.core.signal_bus import SignalBus, Signal

# Maps timeframe → ctrl field names + candle array
_TF_META = {
    TF_30S: ('c30s_seq', 'c30s_widx', 'c30s_bucket', 'candles_30s'),
    TF_1M:  ('c1m_seq',  'c1m_widx',  'c1m_bucket',  'candles_1m'),
    TF_3M:  ('c3m_seq',  'c3m_widx',  'c3m_bucket',  'candles_3m'),
}


class CandleBuilder:
    def __init__(self, shm: ShmStore, symbols: SymbolRegistry,
                 watched: dict[str, list[int]], logger: ShmLogger, bus: SignalBus):
        """
        watched: { "NSE:NIFTY50-INDEX": [TF_30S, TF_1M, TF_3M], ... }
        """
        self._shm     = shm
        self._symbols = symbols
        self._log     = logger
        self._bus     = bus

        self._TF_SIGNAL = {
            TF_30S: Signal.CANDLE_30S_CLOSE,
            TF_1M:  Signal.CANDLE_1M_CLOSE,
            TF_3M:  Signal.CANDLE_3M_CLOSE,
        }

        # Convert to idx-based
        self._watched: dict[int, list[int]] = {
            symbols.idx(sym): tfs for sym, tfs in watched.items()
        }

    
    async def run(self):
        last_widx: dict[int, int | None] = {sym_idx: None for sym_idx in self._watched}

        while True:
            for sym_idx, timeframes in self._watched.items():
                ctrl     = self._shm.ctrl[sym_idx]
                cur_widx = int(ctrl['tick_widx'])

                if last_widx[sym_idx] is None:
                    last_widx[sym_idx] = cur_widx
                    continue

                read_idx = last_widx[sym_idx]

                while read_idx != cur_widx:
                    # ── SEQLOCK ───────────────────────────
                    while True:
                        s1 = int(ctrl['tick_seq'])
                        if s1 & 1:
                            await asyncio.sleep(0)
                            continue
                        tick = self._shm.ticks[sym_idx * MAX_TICKS_PER_SYMBOL + read_idx].copy()
                        s2   = int(ctrl['tick_seq'])
                        if s1 == s2:
                            break
                        await asyncio.sleep(0)
                    # ─────────────────────────────────────────────
                    ts  = float(tick['timestamp'])
                    ltp = float(tick['ltp'])
                    vol = int(tick['volume'])

                    for tf in timeframes:
                        self._process(sym_idx, tf, ts, ltp, vol)

                    read_idx = (read_idx + 1) % MAX_TICKS_PER_SYMBOL

                last_widx[sym_idx] = cur_widx

            await asyncio.sleep(0.005)


    def _process(self, sym_idx: int, tf: int, ts: float, ltp: float, vol: int):
        seq_f, widx_f, bucket_f, arr_attr = _TF_META[tf]
        ctrl   = self._shm.ctrl[sym_idx]
        candles = getattr(self._shm, arr_attr)
        bucket  = int(ts // tf)
        base    = sym_idx * MAX_CANDLE_HISTORY
        widx    = int(ctrl[widx_f])
        last_b  = int(ctrl[bucket_f])

        if last_b == 0:
            # First tick for this symbol+tf
            ctrl[bucket_f] = bucket
            self._open_candle(candles[base + widx], ts, ltp, vol)
            return

        if bucket != last_b:
            # Close current candle
            candles[base + widx]['seq'] += 1
            # Open next slot
            new_widx = (widx + 1) % MAX_CANDLE_HISTORY
            ctrl[bucket_f] = bucket
            ctrl[widx_f]   = new_widx
            ctrl[seq_f]   += 1     # signal to strategy that new candle closed
            self._bus.fire(self._TF_SIGNAL[tf])
            self._open_candle(candles[base + new_widx], ts, ltp, vol)
        else:
            # Update current candle in-place (zero copy)
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
