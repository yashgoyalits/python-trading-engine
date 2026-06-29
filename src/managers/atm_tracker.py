# src/managers/atm_tracker.py
# Background task — NIFTY ATM strike tracker
# SHM se tick padhta hai (candle_builder jaisa pattern),
# sirf tab recalculate karta hai jab LTP 25-point boundary cross kare.
# ATM aur ATM+1 ke 4 symbols (2 CE + 2 PE) continuously subscribed rakhta hai.

import asyncio
from src.logger import log
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TICKS_PER_SYMBOL
from src.symbol_manager.symbol_manager import SymbolManager
from src.strategies.strategy_one.strike_price_helper import atm_strike_price

_INTERVAL = 50
_HALF     = _INTERVAL // 2      # 25 — boundary half-width


def _wanted_strikes(ltp: float) -> set[str]:
    """ATM aur ATM+1 ke CE aur PE — 4 symbols total."""
    return {
        atm_strike_price(ltp,              1),   # ATM CE
        atm_strike_price(ltp,             -1),   # ATM PE
        atm_strike_price(ltp + _INTERVAL,  1),   # ATM+1 CE
        atm_strike_price(ltp + _INTERVAL, -1),   # ATM+1 PE
    }


class ATMTracker:
    """
    NIFTY sym_idx ka tick continuously padhta hai.
    Jab LTP boundary cross kare tabhi ATM recalculate karta hai
    aur SymbolManager mein add/remove karta hai.

    Engine._run() mein support_tasks mein dalo.
    """

    def __init__(
        self,
        shm: ShmStore,
        symbols: SymbolManager,
        sym_idx: int,           # NIFTY50-INDEX ka shm index
    ):
        self._shm      = shm
        self._symbols  = symbols
        self._sym_idx  = sym_idx

        # runtime state
        self._subscribed:  set[str]     = set()
        self._lower_bound: float | None = None   # ATM - 25
        self._upper_bound: float | None = None   # ATM + 25

    # ── entrypoint ────────────────────────────────────────────

    async def run(self) -> None:
        ctrl      = self._shm.ctrl[self._sym_idx]
        tick_base = self._sym_idx * MAX_TICKS_PER_SYMBOL
        last_widx: int | None = None

        log.info("ATMTracker: started")

        try:
            while True:
                await asyncio.sleep(0.001)

                cur_widx = int(ctrl['tick_widx'])

                # ── first tick init ───────────────────────────
                if last_widx is None:
                    last_widx = cur_widx
                    continue

                if last_widx == cur_widx:
                    continue

                # ── process each new tick ─────────────────────
                while last_widx != cur_widx:

                    ltp       = self._read_ltp(ctrl, tick_base, last_widx)
                    last_widx = (last_widx + 1) % MAX_TICKS_PER_SYMBOL

                    if ltp == 0.0:
                        continue

                    # ── boundary check — 99% ticks yahan khatam ──
                    if (
                        self._lower_bound is not None
                        and self._lower_bound < ltp < self._upper_bound
                    ):
                        continue    # strike same hai, kuch nahi karna

                    # ── boundary cross — recalculate ──────────────
                    self._update_strikes(ltp)

        except asyncio.CancelledError:
            log.info("ATMTracker: cancelled — subscriptions cleanup")
            self._cleanup()

    # ── strike update ─────────────────────────────────────────

    def _update_strikes(self, ltp: float) -> None:
        atm    = round(ltp / _INTERVAL) * _INTERVAL
        wanted = _wanted_strikes(ltp)

        to_add    = wanted - self._subscribed
        to_remove = self._subscribed - wanted

        for sym in to_remove:
            self._symbols.remove(sym)

        for sym in to_add:
            self._symbols.add(sym)

        self._subscribed  = wanted
        self._lower_bound = atm - _HALF   # e.g. 24200 - 25 = 24175
        self._upper_bound = atm + _HALF   # e.g. 24200 + 25 = 24225

        log.info(
            f"ATMTracker: ATM={atm} | "
            f"boundary=({self._lower_bound}, {self._upper_bound}) | "
            f"+{len(to_add)} -{len(to_remove)} symbols"
        )

    # ── seqlock read ──────────────────────────────────────────

    def _read_ltp(self, ctrl, tick_base: int, widx: int) -> float:
        """Seqlock-safe LTP read — candle_builder jaisa pattern."""
        while True:
            s1 = int(ctrl['tick_seq'])
            if s1 & 1:
                # writer busy — spin
                continue
            ltp = float(self._shm.ticks[tick_base + widx]['ltp'])
            s2  = int(ctrl['tick_seq'])
            if s1 == s2:
                return ltp

    # ── cleanup on cancel ─────────────────────────────────────

    def _cleanup(self) -> None:
        self._subscribed.clear()
        log.info("ATMTracker: all ATM subscriptions removed")