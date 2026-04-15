import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TICKS_PER_SYMBOL
from src.managers.active_trades import ActiveTradesManager
from src.broker.fyers.order_placement import FyersOrderPlacement
from src.infrastructure.logger import ShmLogger

class TrailingManager:
    def __init__(self, trades: ActiveTradesManager, placement: FyersOrderPlacement, logger: ShmLogger):
        self._trades   = trades
        self._place    = placement
        self._log      = logger

    async def run(self, sym_idx: int, shm: ShmStore, event: asyncio.Event):

        while True:
            await event.wait()

            last_seq = 0
            self._log.info("TrailingManager: active, ticks watch kar raha hai")

            ctrl      = shm.ctrl[sym_idx]          
            tick_base = sym_idx * MAX_TICKS_PER_SYMBOL  

            while True:
                trade = self._trades.get_active()
                if trade is None:
                    event.clear()
                    self._log.info("TrailingManager: trade closed, so raha hai")
                    break

                cur_seq = int(ctrl['tick_seq'])     
                if cur_seq == last_seq:
                    await asyncio.sleep(0)
                    continue

                last_seq = cur_seq

                # Seqlock
                while True:
                    s1 = int(ctrl['tick_seq'])
                    if s1 % 2 == 1:
                        continue
                    widx = int(ctrl['tick_widx'])
                    tick = shm.ticks[tick_base + (widx - 1) % MAX_TICKS_PER_SYMBOL].copy()
                    s2   = int(ctrl['tick_seq'])
                    if s1 == s2:
                        break

                await self._check_levels(tick, trade)
                await asyncio.sleep(0)


    async def _check_levels(self, tick, active_trade):

        print(tick)