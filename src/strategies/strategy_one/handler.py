# src/strategies/strategy_one/handler.py
import asyncio
from src.logger import log
from src.core.shm_store import ShmStore
from src.infrastructure.symbol_manager import SymbolManager
from src.trade_manager import IActiveTradeManager
from src.executor.base_executor import BaseExecutor
from src.strategies.strategy_one.entry_detection import EntryDetectionLoop
from src.strategies.strategy_one.order_monitor import OrderMonitor
from src.strategies.strategy_one.trailing import TrailingManager

class StrategyHandler:
    def __init__(
        self,
        shm: ShmStore,
        symbols: SymbolManager,
        trades: IActiveTradeManager,
        executor: BaseExecutor,
        config: dict,
    ):
        self._shm      = shm
        self._trades   = trades
        self._executor = executor
        self._sid      = config['id']
        self._max      = config['max_trades']
        self._done     = 0

        sym_name      = config['symbols'][0]   # baad mein dynamic
        self._sym_idx = symbols.idx(sym_name)

        # Order params — handler place karega
        ocfg              = config['order']
        self._sym         = sym_name           # baad mein strike dynamic hoga
        self._qty         = ocfg['qty']
        self._order_type  = ocfg['order_type']
        self._stop_loss   = ocfg['stop_loss']
        self._take_profit = ocfg['take_profit']

        # Events
        self._trade_closed_event = asyncio.Event()
        self._trailing_event     = asyncio.Event()

        # Sub-components — sirf zaroorat ki cheezein pass karo
        self._entry_loop = EntryDetectionLoop(
            shm=shm,
            sym_idx=self._sym_idx,
            strategy_id=self._sid,
            config=config,
        )
        self._order_monitor = OrderMonitor(
            shm=shm,
            trades=trades,
            trailing_event=self._trailing_event,
            trade_closed_event=self._trade_closed_event,
            strategy_id=self._sid,
            trailing_cfg=config['trailing'],
        )
        self._trailing = TrailingManager(trades, executor)

    # ── main lifecycle ────────────────────────────────────────

    async def run(self):
        log.info(f"[{self._sid}] Starting — max trades: {self._max}")

        while self._done < self._max:

            # ── 1. Entry signal wait karo ─────────────────────
            side = await self._entry_loop.run()
            log.info(f"[{self._sid}] Signal: side={side}")

            # ── 2. Handler place karta hai ────────────────────
            res = await self._executor.place_order(
                symbol="NSE:IDEA-EQ",
                qty=self._qty,
                order_type=self._order_type,
                side=side,
                stop_loss=self._stop_loss,
                take_profit=self._take_profit,
            )

            if res.get('code') != 1101:
                log.error(f"[{self._sid}] Order failed: {res}")
                continue   # dobara signal dhundho

            order_id    = res.get('id', '')
            self._done += 1
            self._trades.add_trade(self._done, order_id)
            log.info(f"[{self._sid}] Trade #{self._done} placed | {order_id}")

            # ── 3. Monitor + trailing start karo ─────────────
            monitor_task = asyncio.create_task(
                self._order_monitor.run(),
                name=f"{self._sid}_monitor",
            )
            trailing_task = asyncio.create_task(
                self._trailing.run(self._sym_idx, self._shm, self._trailing_event),
                name=f"{self._sid}_trailing",
            )

            # ── 4. Trade close hone tak block karo ───────────
            await self._trade_closed_event.wait()

            # ── 5. Reset + tasks band karo ────────────────────
            self._trade_closed_event.clear()
            self._trailing_event.clear()

            monitor_task.cancel()
            trailing_task.cancel()
            await asyncio.gather(monitor_task, trailing_task, return_exceptions=True)

            log.info(f"[{self._sid}] Trade #{self._done} closed")

        log.info(f"[{self._sid}] Max trades reached. Done.")