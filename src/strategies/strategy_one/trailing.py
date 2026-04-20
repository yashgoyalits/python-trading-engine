import asyncio
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TICKS_PER_SYMBOL
from src.managers.active_trades import ActiveTradesManager
from src.executor.base_executor import BaseExecutor
from src.infrastructure.logger import ShmLogger

class TrailingManager:
    def __init__(self, trades: ActiveTradesManager, executor: BaseExecutor, logger: ShmLogger):
        self._trades   = trades
        self._executor = executor
        self._log      = logger

    
    async def run(self, sym_idx: int, shm: ShmStore, event: asyncio.Event):
        ctrl      = shm.ctrl[sym_idx]
        tick_base = sym_idx * MAX_TICKS_PER_SYMBOL

        while True:
            await event.wait()

            last_seq = int(ctrl['tick_seq'])
            self._log.info("TrailingManager: active, ticks watch kar raha hai")

            while True:
                trade = self._trades.get_active()
                if trade is None:
                    event.clear()
                    self._log.info("TrailingManager: trade closed, so raha hai")
                    break

                await asyncio.sleep(0.001)

                cur_seq = int(ctrl['tick_seq'])
                if cur_seq == last_seq:
                    continue

                last_seq = cur_seq

                while True:
                    s1 = int(ctrl['tick_seq'])
                    if s1 & 1:
                        await asyncio.sleep(0)
                        continue
                    widx = int(ctrl['tick_widx'])
                    s2   = int(ctrl['tick_seq'])
                    if s1 == s2:
                        break

                slot = shm.ticks[tick_base + (widx - 1) % MAX_TICKS_PER_SYMBOL]
                await self._check_levels(slot, trade)


    async def _check_levels(self, tick, active_trade_view):
        ltp   = float(tick['ltp'])
        count = int(active_trade_view['trailing_count'])
        if count == 0:
            return
 
        stop_oid = active_trade_view['stop_order_id'].tobytes().rstrip(b'\x00').decode()
        qty      = int(active_trade_view['qty'])
 
        for i in range(count):
            lvl = active_trade_view['trailing'][i]
            if bool(lvl['hit']):
                continue
 
            if ltp > float(lvl['threshold']):
                self._log.info("I want to place and modify order")
                active_trade_view['trailing'][i]['hit'] = True
                # res = await self._place.modify_order(
                #     stop_oid,
                #     order_type=4,
                #     limit_price=float(lvl['new_stop']),
                #     stop_price=float(lvl['new_stop']),
                #     qty=qty,
                # )
                # if res.get('code') == 1102:
                #     # Hit flag seedha SHM mein likho
                #     active_trade_view['trailing'][i]['hit'] = True
                #     self._log.info(f"TrailingManager: level {i} hit | LTP {ltp}")
                # else:
                #     self._log.error(f"TrailingManager: modify failed level {i} | {res}")
 