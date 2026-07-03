import asyncio
import time 
from src.logger import log
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TICKS_PER_SYMBOL
from src.trade_manager import IActiveTradeManager
from src.executor.base_executor import BaseExecutor

class TrailingManager:
    def __init__(self, trade_mgr: IActiveTradeManager, executor: BaseExecutor):
        self._trade_mgr   = trade_mgr
        self._executor = executor

        self._last_modify_ts = 0.0
        self._modify_gap = 20.0  
    
    async def run(self, sym_idx: int, shm: ShmStore, event: asyncio.Event):
        ctrl      = shm.ctrl[sym_idx]
        tick_base = sym_idx * MAX_TICKS_PER_SYMBOL

        while True:
            await event.wait()

            last_read_widx = int(ctrl['tick_widx'])     # ← event fire hone ke waqt se start

            while True:
                trade = self._trade_mgr.get_active()
                if trade is None:
                    event.clear()
                    log.info("TrailingManager: trade closed")
                    break

                await asyncio.sleep(0.001)

                cur_widx = int(ctrl['tick_widx'])

                while last_read_widx != cur_widx:       
                    # ── SEQLOCK — slot read lock ke ANDAR ────────────
                    while True:
                        s1 = int(ctrl['tick_seq'])
                        if s1 & 1:
                            await asyncio.sleep(0)
                            continue

                        # data read between s1 and s2
                        slot = shm.ticks[tick_base + last_read_widx]
                        ltp  = float(slot['ltp'])

                        s2 = int(ctrl['tick_seq'])
                        if s1 == s2:
                            break
                    # ─────────────────────────────────────────────────

                    await self._check_levels(ltp, trade)
                    last_read_widx = (last_read_widx + 1) % MAX_TICKS_PER_SYMBOL


    async def _check_levels(self, ltp, active_trade):
        trailing_lvls = int(active_trade['trailing_count'])
        side = int(active_trade['side'])
        
        if trailing_lvls == 0:
            log.error("No Trailing Levels Found")
            return

        trade_id = active_trade['order_id'].tobytes().rstrip(b'\x00').decode()
        stop_oid = active_trade['stop_order_id'].tobytes().rstrip(b'\x00').decode()

        for i in range(trailing_lvls):
            lvl = active_trade['trailing'][i]
            
            # If trailing level is already hit skip
            if bool(lvl['hit']):
                continue

            log.info(
                f"LTP={ltp} | Level={i} | "
                f"Threshold={float(lvl['threshold'])} | "
                f"New SL={float(lvl['new_stop'])} | "
                f"Side={side} | "
                f"Hit={bool(lvl['hit'])}"
            )          
 
            if ltp > lvl['threshold'] if side == 1 else ltp < lvl['threshold']:

                # Modify Order Cooldown
                now = time.monotonic()
                if now - self._last_modify_ts < self._modify_gap:
                    log.info("Modify cooldown active")
                    continue

                # Modify Order
                log.info("I want to place and modify order")
                res = await self._executor.modify_order(
                    stop_oid,
                    order_type=4,
                    limit_price=float(lvl['new_stop']) - 0.10,
                    stop_price=float(lvl['new_stop']),
                    qty=int(active_trade['qty']),
                )
                if res.get('code') == 1102:
                    self._trade_mgr.mark_trailing_hit(trade_id, i)
                    self._last_modify_ts = now
                    log.info(f"Order Modify")
                    log.info(f"level {i} hit | LTP {ltp}")
                else:
                    log.error(f"TrailingManager: order modify failed level {i} | {res}")
                    self._last_modify_ts = now