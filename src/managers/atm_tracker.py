# src/managers/atm_tracker.py
# Background task — NIFTY ATM strike tracker
# SHM se tick padhta hai (candle_builder jaisa pattern),
# sirf tab recalculate karta hai jab LTP boundary cross kare.
# WINDOW_RADIUS ke (2*WINDOW_RADIUS+1) strikes (CE + PE each) continuously subscribed rakhta hai.

import asyncio
from src.logger import log
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TICKS_PER_SYMBOL
from src.symbol_manager.subscription_manager import SubscriptionManager
from src.strategies.strategy_one.strike_price_helper import atm_strike_price

_STRIKE_INTERVAL = 50
_WINDOW_RADIUS   = 2
_STEP            = _STRIKE_INTERVAL * (_WINDOW_RADIUS + 1)   # 150
_BOUNDARY_OFFSET = _WINDOW_RADIUS * _STRIKE_INTERVAL + _STRIKE_INTERVAL // 2   # 125


def _window_symbols(center: int) -> set[str]:
    """CE + PE for each strike in [center - RADIUS*INTERVAL, ..., center + RADIUS*INTERVAL]."""
    symbols = set()
    for i in range(-_WINDOW_RADIUS, _WINDOW_RADIUS + 1):
        strike = center + i * _STRIKE_INTERVAL
        symbols.add(atm_strike_price(strike,  1))   # CE
        symbols.add(atm_strike_price(strike, -1))   # PE
    return symbols


class ATMTracker:
    """
    NIFTY sym_idx ka tick continuously padhta hai.
    Jab LTP boundary cross kare tabhi center shift karta hai
    aur SubscriptionManager ke through add/remove karta hai.

    Engine._run() mein support_tasks mein dalo.
    """

    def __init__(
        self,
        shm: ShmStore,
        sym_sub_mgr: SubscriptionManager,
        sym_idx: int,
    ):
        self._shm         = shm
        self._sym_sub_mgr = sym_sub_mgr
        self._sym_idx     = sym_idx

        self._subscribed:  set[str]     = set()
        self._center:      int | None   = None
        self._lower_bound: float | None = None
        self._upper_bound: float | None = None

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

                if last_widx is None:
                    last_widx = cur_widx
                    continue

                if last_widx == cur_widx:
                    continue

                while last_widx != cur_widx:
                    ltp       = self._read_ltp(ctrl, tick_base, last_widx)
                    last_widx = (last_widx + 1) % MAX_TICKS_PER_SYMBOL

                    if ltp == 0.0:
                        continue

                    # ── first valid tick — init center ────────────────────
                    if self._center is None:
                        self._center = round(ltp / _STRIKE_INTERVAL) * _STRIKE_INTERVAL
                        self._update_bounds()
                        log.info(f"ATMTracker: init")
                        self._rebalance()
                        continue

                    # ── steady-state: 99% ticks yahan khatam ─────────────
                    if self._lower_bound < ltp < self._upper_bound:
                        continue

                    # ── boundary cross — center shift ─────────────────────
                    # `while` zaroori hai: ek bade jump mein LTP single shift
                    # ke baad bhi naye window ke bahar ho sakta hai.
                    if ltp < self._lower_bound:
                        while ltp < self._lower_bound:
                            self._center -= _STEP
                            self._update_bounds()
                    else:
                        while ltp > self._upper_bound:
                            self._center += _STEP
                            self._update_bounds()

                    self._rebalance()

        except asyncio.CancelledError:
            log.info("ATMTracker: cancelled — subscriptions cleanup")
            self._cleanup()

    # ── helpers ───────────────────────────────────────────────

    def _update_bounds(self) -> None:
        self._lower_bound = self._center - _BOUNDARY_OFFSET
        self._upper_bound = self._center + _BOUNDARY_OFFSET

    def _rebalance(self) -> None:
        wanted = _window_symbols(self._center)

        # Remove-before-add: MAX_SYMBOLS breach se bachao
        to_remove = self._subscribed - wanted
        to_add    = wanted - self._subscribed

        for sym in to_remove:
            self._sym_sub_mgr.remove(sym)

        for sym in to_add:
            self._sym_sub_mgr.add(sym)

        self._subscribed = wanted

        log.info(
            f"ATMTracker: center={self._center} | "
            f"boundary=({self._lower_bound}, {self._upper_bound}) | "
            f"+{len(to_add)} -{len(to_remove)}"
        )

    def _read_ltp(self, ctrl, tick_base: int, widx: int) -> float:
        """Seqlock-safe LTP read — candle_builder jaisa pattern."""
        while True:
            s1 = int(ctrl['tick_seq'])
            if s1 & 1:
                continue
            ltp = float(self._shm.ticks[tick_base + widx]['ltp'])
            s2  = int(ctrl['tick_seq'])
            if s1 == s2:
                return ltp

    def _cleanup(self) -> None:
        # Broker WS is shutting down moments after this — unsubscribing is
        # unnecessary and triggers Fyers -300 errors. Just drop local state.
        self._subscribed.clear()
        log.info("ATMTracker: all ATM subscriptions removed")