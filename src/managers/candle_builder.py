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

        # Convert to idx-based
        self._watched: dict[int, list[int]] = {
            symbols.idx(sym): tfs for sym, tfs in watched.items()
        }
        # Track last seen tick_seq per symbol
        self._last_tick_seq = [0] * MAX_SYMBOLS

    async def run(self):
        while True:
            for sym_idx, timeframes in self._watched.items():
                cur_seq = int(self._shm.ctrl[sym_idx]['tick_seq'])
                if cur_seq == self._last_tick_seq[sym_idx]:
                    continue

                self._last_tick_seq[sym_idx] = cur_seq

                # Read latest tick (widx points to NEXT write slot, so -1 is latest)
                # Reader seqlock
                ctrl = self._shm.ctrl[sym_idx]
                while True:
                    s1 = int(ctrl['tick_seq'])
                    widx   = int(ctrl['tick_widx'])
                    latest = (widx - 1) % MAX_TICKS_PER_SYMBOL
                    tick   = self._shm.ticks[sym_idx * MAX_TICKS_PER_SYMBOL + latest].copy()
                    s2     = int(ctrl['tick_seq'])
                    if s1 == s2:
                        break

                ts  = float(tick['timestamp'])
                ltp = float(tick['ltp'])
                vol = int(tick['volume'])

                for tf in timeframes:
                    self._process(sym_idx, tf, ts, ltp, vol)

            await asyncio.sleep(0)  # yield — no blocking, no queue

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
            ctrl[widx_f]   = new_widx
            ctrl[bucket_f] = bucket
            ctrl[seq_f]   += 1     # signal to strategy that new candle closed
            self._bus.fire(Signal.CANDLE_30S_CLOSE)
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
