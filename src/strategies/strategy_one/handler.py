# src/strategies/strategy_one/handler.py
import asyncio
from src.logger import log
from src.db import csv
from src.core.shm_store import ShmStore
from src.symbol_manager.symbol_manager import SymbolManager
from src.symbol_manager.subscription_manager import SubscriptionManager
from src.trade_manager import IActiveTradeManager
from src.executor.base_executor import BaseExecutor
from src.strategies.strategy_one.entry_detection import EntryDetectionLoop
from src.strategies.strategy_one.order_monitor import OrderMonitor
from src.strategies.strategy_one.trailing import TrailingManager
from src.strategies.strategy_one.strike_price_helper import atm_strike_price

class StrategyHandler:
    def __init__(
        self,
        shm: ShmStore,
        symbols: SymbolManager,
        trades: IActiveTradeManager,
        executor: BaseExecutor,
        config: dict,
        sym_sub_mgr: SubscriptionManager,
    ):
        self._shm      = shm
        self._trades   = trades
        self._executor = executor
        self._sid      = config['id']
        self._max      = config['max_trades']
        self._done     = 0
        self._symbols = symbols
        self._sym_sub_mgr = sym_sub_mgr

        # Entry Symbol from Config
        sym_name = config['entry_symbol']
        self._sym_idx = symbols.idx(sym_name)

        # Order params from Config
        ocfg              = config['order']
        self._qty         = ocfg['qty']
        self._order_type  = ocfg['order_type']
        self._stop_loss   = ocfg['stop_loss']
        self._take_profit = ocfg['take_profit']

        # Events
        self._trade_closed_event = asyncio.Event()
        self._trailing_event     = asyncio.Event()

        # Sub-components — sirf zaroorat ki cheezein pass karo
        self._entry_detection_loop = EntryDetectionLoop(
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

        # ── Monitor ek baar start karo — hamesha chalta rahega ──
        monitor_task = asyncio.create_task(
            self._order_monitor.run(),          
            name=f"{self._sid}_monitor",
        )

        try:
            while self._done < self._max:

                # ── Entry Detection Lopp ────────────────────────
                side, close_price = await self._entry_detection_loop.run()
                log.info(f"[{self._sid}] Signal: side={side}, {close_price}")

                # Strike price calculation  ────────────────────────
                strike_price = atm_strike_price(close_price, side)
                log.info(f"[{self._sid}] ATM Symbol: {strike_price}")

                # Order Placement  ───────────────────────────────────────
                try:
                    res = await self._executor.place_order(
                        symbol="NSE:IDEA-EQ",
                        qty=self._qty,
                        order_type=self._order_type,
                        side=side,
                        stop_loss=self._stop_loss,
                        take_profit=self._take_profit,
                    )
                except Exception as e:
                    log.error(f"[{self._sid}] place_order raised unexpectedly: {e}")
                    continue

                if res.get('code') != 1101:
                    log.error(f"[{self._sid}] Order failed: {res}")
                    continue

                order_id     = res.get('id', '')
                self._done  += 1
                self._trades.add_trade(self._done, order_id)
                log.info(f"[{self._sid}] Trade #{self._done} placed | {order_id}")

                # Subscribe Strike Price ───────────────────────────────────────
                option_sym_idx = self._sym_sub_mgr.ensure(strike_price)
                
                # Trailing Task ───────────────────────────────────────
                trailing_task = asyncio.create_task(
                    self._trailing.run(option_sym_idx, self._shm, self._trailing_event),
                    name=f"{self._sid}_trailing",
                )

                await self._trade_closed_event.wait()

                # Log Trade After Closed ───────────────────────────────────────
                trade = self._trades.get_active()
                trade_id = trade['order_id'].tobytes().rstrip(b'\x00').decode()
                csv.log_close(trade)
                self._trades.close_trade(trade_id)

                # Clear Events ───────────────────────────────────────
                self._trade_closed_event.clear()
                self._trailing_event.clear()

                # Cancel Trailing Task ───────────────────────────────────────
                trailing_task.cancel()
                await asyncio.gather(trailing_task, return_exceptions=True)

                log.info(f"[{self._sid}] Trade #{self._done} closed")

        finally:
            monitor_task.cancel()
            await asyncio.gather(monitor_task, return_exceptions=True)

        log.info(f"[{self._sid}] Max trades reached. Done.")