# src/executor/dummy_executor.py

import asyncio
from uuid import uuid4
from src.executor.base_executor import BaseExecutor
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TICKS_PER_SYMBOL, MAX_ORDERS
from src.logger import log


class DummyExecutor(BaseExecutor):

    def __init__(self, shm: ShmStore, sym_idx: int):
        self._shm       = shm
        self._sym_idx   = sym_idx
        self._connected = False
        self._exit_task: asyncio.Task | None = None

        self._active     = False
        self._parent_id  = ""
        self._sl_id      = ""
        self._tp_id      = ""
        self._sl_price   = 0.0
        self._tp_price   = 0.0
        self._qty        = 0
        self._symbol     = ""

    # ── lifecycle ──────────────────────────────────────────────

    async def connect(self) -> None:
        self._connected = True
        self._exit_task = asyncio.create_task(
            self._watch_exit(), name="dummy_exit_watcher"
        )
        log.info("DummyExecutor: connected (forward test mode)")

    def is_connected(self) -> bool:
        return self._connected

    async def disconnect(self) -> None:
        self._connected = False
        if self._exit_task:
            self._exit_task.cancel()
            await asyncio.gather(self._exit_task, return_exceptions=True)
        log.info("DummyExecutor: disconnected")

    # ── order ops ─────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        qty: int,
        order_type: int,
        side: int,
        stop_loss: float,
        take_profit: float,
    ) -> dict:

        ctrl = self._shm.ctrl[self._sym_idx]
        widx = (int(ctrl['tick_widx']) - 1) % MAX_TICKS_PER_SYMBOL
        ltp  = float(self._shm.ticks[self._sym_idx * MAX_TICKS_PER_SYMBOL + widx]['ltp'])

        if ltp == 0.0:
            log.error("DummyExecutor: LTP is 0 — tick data abhi nahi aayi")
            return {"code": -1, "message": "no tick data"}

        pid   = f"D_{uuid4().hex[:8]}"
        sl_id = f"D_SL_{uuid4().hex[:8]}"
        tp_id = f"D_TP_{uuid4().hex[:8]}"

        sl_price = round(ltp - stop_loss,   2) if side == 1 else round(ltp + stop_loss,   2)
        tp_price = round(ltp + take_profit, 2) if side == 1 else round(ltp - take_profit, 2)

        log.info(
            f"DummyExecutor: place_order | {symbol} | LTP={ltp} "
            f"SL={sl_price} TP={tp_price} | pid={pid}"
        )

        # ── state pehle save karo ─────────────────────────────
        # zaroori hai — _on_trade_placed pehle chalega, fills baad mein
        self._active    = True
        self._parent_id = pid
        self._sl_id     = sl_id
        self._tp_id     = tp_id
        self._sl_price  = sl_price
        self._tp_price  = tp_price
        self._qty       = qty
        self._symbol    = symbol

        # ── fills defer karo ──────────────────────────────────
        # _on_trade_placed ko pehle run hone do, tab fills likhenge
        asyncio.create_task(
            self._write_fills_deferred(
                pid, sl_id, tp_id,
                ltp, sl_price, tp_price,
                qty, side, order_type, symbol,
            ),
            name="dummy_fills"
        )

        return {"code": 1101, "id": pid}

    async def modify_order(
        self,
        order_id: str,
        order_type: int,
        limit_price: float,
        stop_price: float,
        qty: int,
    ) -> dict:

        log.info(
            f"DummyExecutor: modify_order | {order_id} "
            f"new_stop={stop_price} new_limit={limit_price}"
        )

        self._write_order({
            "status": 6, "type": order_type, "side": 0,
            "qty": qty, "tradedPrice": 0.0,
            "stopPrice": stop_price, "limitPrice": limit_price,
            "id": order_id, "parentId": self._parent_id,
            "symbol": self._symbol,
        })

        # exit watcher naye SL pe kaam karega
        self._sl_price = stop_price

        return {"code": 1102}

    # ── deferred fills ────────────────────────────────────────

    async def _write_fills_deferred(
        self,
        pid: str, sl_id: str, tp_id: str,
        ltp: float, sl_price: float, tp_price: float,
        qty: int, side: int, order_type: int, symbol: str,
    ):
        # _on_trade_placed ko run hone do pehle
        await asyncio.sleep(0.05)

        # parent fill (status=2 → filled)
        self._write_order({
            "status": 2, "type": order_type, "side": side,
            "qty": qty, "tradedPrice": ltp,
            "stopPrice": 0.0, "limitPrice": 0.0,
            "id": pid, "parentId": "", "symbol": symbol,
        })

        await asyncio.sleep(0.01)

        # SL child (status=6 → open, type=4 → SL)
        self._write_order({
            "status": 6, "type": 4, "side": -side,
            "qty": qty, "tradedPrice": 0.0,
            "stopPrice": sl_price, "limitPrice": sl_price,
            "id": sl_id, "parentId": pid, "symbol": symbol,
        })

        await asyncio.sleep(0.01)

        # TP child (status=6 → open, type=1 → limit)
        self._write_order({
            "status": 6, "type": 1, "side": -side,
            "qty": qty, "tradedPrice": 0.0,
            "stopPrice": 0.0, "limitPrice": tp_price,
            "id": tp_id, "parentId": pid, "symbol": symbol,
        })

        log.info(
            f"DummyExecutor: fills written | "
            f"parent={pid} sl={sl_id} tp={tp_id}"
        )

    # ── exit watcher ──────────────────────────────────────────

    async def _watch_exit(self):
        ctrl      = self._shm.ctrl[self._sym_idx]
        tick_base = self._sym_idx * MAX_TICKS_PER_SYMBOL
        last_widx = int(ctrl['tick_widx'])

        try:
            while True:
                await asyncio.sleep(0.001)

                if not self._active:
                    continue

                cur_widx = int(ctrl['tick_widx'])

                while last_widx != cur_widx:
                    ltp = float(self._shm.ticks[tick_base + last_widx]['ltp'])

                    # SL hit
                    if ltp <= self._sl_price:
                        log.info(
                            f"DummyExecutor: SL hit | LTP={ltp} SL={self._sl_price}"
                        )
                        self._write_order({
                            "status": 2, "type": 4, "side": 0,
                            "qty": self._qty, "tradedPrice": ltp,
                            "stopPrice": self._sl_price,
                            "limitPrice": self._sl_price,
                            "id": self._sl_id,
                            "parentId": self._parent_id,
                            "symbol": self._symbol,
                        })
                        self._active = False
                        break

                    # TP hit
                    if ltp >= self._tp_price:
                        log.info(
                            f"DummyExecutor: TP hit | LTP={ltp} TP={self._tp_price}"
                        )
                        self._write_order({
                            "status": 2, "type": 1, "side": 0,
                            "qty": self._qty, "tradedPrice": ltp,
                            "stopPrice": 0.0,
                            "limitPrice": self._tp_price,
                            "id": self._tp_id,
                            "parentId": self._parent_id,
                            "symbol": self._symbol,
                        })
                        self._active = False
                        break

                    last_widx = (last_widx + 1) % MAX_TICKS_PER_SYMBOL

                if not self._active:
                    last_widx = int(ctrl['tick_widx'])

        except asyncio.CancelledError:
            log.info("DummyExecutor: exit watcher cancelled")

    # ── internal write ────────────────────────────────────────

    def _write_order(self, o: dict):
        ctrl = self._shm.order_ctrl[0]
        widx = int(ctrl['widx'])
        slot = self._shm.orders[widx]

        ctrl['seq'] += 1
        slot['status']         = o.get("status", 0)
        slot['order_type']     = o.get("type", 0)
        slot['side']           = o.get("side", 0)
        slot['qty']            = o.get("qty", 0)
        slot['stop_price']     = o.get("stopPrice", 0.0)
        slot['limit_price']    = o.get("limitPrice", 0.0)
        slot['traded_price']   = o.get("tradedPrice", 0.0)
        slot['order_id']       = (o.get("id",       "") or "").encode()[:64]
        slot['parent_id']      = (o.get("parentId", "") or "").encode()[:64]
        slot['symbol']         = (o.get("symbol",   "") or "").encode()[:32]
        slot['order_datetime'] = b""
        ctrl['seq'] += 1
        ctrl['widx'] = (widx + 1) % MAX_ORDERS