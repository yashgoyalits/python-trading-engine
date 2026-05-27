# src/managers/candle_builder.py
import time
import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TICKS_PER_SYMBOL, MAX_CANDLE_HISTORY
from src.symbol_manager.symbol_manager import SymbolManager


class CandleBuilder:
    def __init__(self, shm: ShmStore, manager: SymbolManager):
        self._shm     = shm
        self._manager = manager
        # tf_value → sub-array slot index, e.g. {30: 0, 60: 1, 180: 2}
        self._tf_map: dict[int, int] = shm.tf_map

    # ── entrypoint ────────────────────────────────────────────

    async def run(self):
        # Har tf ke liye ek timer task
        timer_tasks = [
            asyncio.create_task(
                self._run_timer(tf), name=f"candle_timer_{tf}"
            )
            for tf in self._tf_map
        ]

        try:
            await self._tick_loop()
        finally:
            for t in timer_tasks:
                t.cancel()
            await asyncio.gather(*timer_tasks, return_exceptions=True)

    # ── tick loop — sirf OHLCV update ────────────────────────

    async def _tick_loop(self):
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
                        self._update_candle(sym_idx, tf, ts, ltp, vol)

                    read_idx = (read_idx + 1) % MAX_TICKS_PER_SYMBOL

                last_widx[sym_idx] = cur_widx

            await asyncio.sleep(0.001)

    # ── timer task — exact boundary par candle close ─────────

    async def _run_timer(self, tf: int):
        while True:
            # Wall clock se next boundary calculate karo
            wall_now  = time.time()
            next_wall = (int(wall_now) // tf + 1) * tf
            sleep_for = next_wall - wall_now

            await asyncio.sleep(sleep_for)

            # Sab registered symbols ke liye candle close karo
            for sym_idx in self._manager.subscriptions():
                self._close_candle(sym_idx, tf, next_wall)

    # ── candle close — timer se trigger hota hai ─────────────

    def _close_candle(self, sym_idx: int, tf: int, boundary_ts: float):
        ctrl    = self._shm.ctrl[sym_idx]
        candles = self._shm.candles[tf]
        tf_idx  = self._tf_map[tf]
        base    = sym_idx * MAX_CANDLE_HISTORY

        widx = int(ctrl['tf_widx'][tf_idx])

        # Agar candle kabhi open hi nahi hui (no ticks in this period)
        # toh close karne ki zaroorat nahi
        if candles[base + widx]['open'] == 0.0:
            return

        # Close current candle
        candles[base + widx]['seq'] += 1

        # Next slot open karo
        new_widx = (widx + 1) % MAX_CANDLE_HISTORY
        ctrl['tf_widx'][tf_idx]  = new_widx
        ctrl['tf_seq'][tf_idx]  += 1          # entry detection ko signal

        # Next candle blank — pehla tick aayega tab open hoga
        slot = candles[base + new_widx]
        slot['open']       = 0.0
        slot['high']       = 0.0
        slot['low']        = 0.0
        slot['close']      = 0.0
        slot['volume']     = 0
        slot['start_time'] = boundary_ts
        slot['seq']        = 0

    # ── OHLCV update — tick se trigger hota hai ──────────────

    def _update_candle(self, sym_idx: int, tf: int, ts: float, ltp: float, vol: int):
        ctrl    = self._shm.ctrl[sym_idx]
        candles = self._shm.candles[tf]
        tf_idx  = self._tf_map[tf]
        base    = sym_idx * MAX_CANDLE_HISTORY

        widx = int(ctrl['tf_widx'][tf_idx])
        c    = candles[base + widx]

        # Pehla tick — candle open karo
        if c['open'] == 0.0:
            c['open']       = ltp
            c['high']       = ltp
            c['low']        = ltp
            c['close']      = ltp
            c['volume']     = vol
            c['start_time'] = ts
            return

        # Baad ke ticks — sirf update karo
        if ltp > c['high']: c['high'] = ltp
        if ltp < c['low']:  c['low']  = ltp
        c['close']  = ltp
        c['volume'] += vol