import asyncio
from typing import Callable
from src.logger import log
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_CANDLE_HISTORY
from src.trade_store import ITradeStore
from src.executor.base_executor import BaseExecutor
from src.strategies.strategy_one.logic import StrategyLogicManager

class EntryDetectionLoop:
    def __init__(
        self,
        shm: ShmStore,
        sym_idx: int,
        trades: ITradeStore,
        executor: BaseExecutor,
        strategy_id: str,
        on_trade_placed: Callable[[str], None],
        is_max_reached: Callable[[], bool],
    ):
        self._shm      = shm
        self._sym_idx  = sym_idx
        self._trades   = trades
        self._executor = executor
        self._sid      = strategy_id
        self._logic    = StrategyLogicManager()

        self._on_trade_placed = on_trade_placed
        self._is_max_reached  = is_max_reached

    # ── main loop ─────────────────────────────────────────────

    async def run(self):
        base     = self._sym_idx * MAX_CANDLE_HISTORY
        ctrl     = self._shm.ctrl[self._sym_idx]
        last_seq = int(ctrl['c30s_seq'])          # pehla seq capture — skip initial fire

        try:
            while True:
                await asyncio.sleep(0.001)

                cur_seq = int(ctrl['c30s_seq'])
                if cur_seq == last_seq:
                    continue

                last_seq = cur_seq

                widx   = int(ctrl['c30s_widx'])
                cidx   = (widx - 1) % MAX_CANDLE_HISTORY
                candle = self._shm.candles_30s[base + cidx]

                trade = self._trades.get_active()

                if trade is None:
                    if self._is_max_reached():
                        log.info(
                            f"[{self._sid}] Max trade limit reached. Stopping candle loop."
                        )
                        return

                    if self._logic.check_entry(candle):
                        await self._enter()

        except asyncio.CancelledError:
            log.info(f"[{self._sid}] candle_loop cancelled.")

    # ── entry ─────────────────────────────────────────────────

    async def _enter(self):
        res = await self._executor.place_order(
            symbol="NSE:IDEA-EQ", qty=1, order_type=2,
            side=1, stop_loss=0.5, take_profit=2.0,
        )
        if res.get('code') == 1101:
            self._on_trade_placed(res.get("id", ""))
        else:
            log.error(f"[{self._sid}] Order placement failed: {res}")
