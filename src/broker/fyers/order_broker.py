import os
import asyncio
from fyers_apiv3.FyersWebsocket import order_ws
from dotenv import load_dotenv

from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ORDERS
from src.infrastructure.logger import ShmLogger

load_dotenv()


class FyersOrderBroker:
    def __init__(self, shm: ShmStore, logger: ShmLogger):
        self._shm   = shm
        self._log   = logger
        self._loop  = None
        self._connected = False

        client_id = os.getenv("CLIENT_ID")
        token     = os.getenv("FYERS_ACCESS_TOKEN")

        self._fyers = order_ws.FyersOrderSocket(
            access_token=f"{client_id}:{token}",
            write_to_file=False,
            log_path=None,
            on_connect=self._on_open,
            on_close=self._on_close,
            on_error=self._on_error,
            on_orders=self._on_order,
            on_positions=self._on_position,
            on_trades=lambda _: None,
        )

    def is_connected(self) -> bool:
        return self._connected

    def connect(self, loop: asyncio.AbstractEventLoop):
        self._loop   = loop
        self._running = True
        self._thread = threading.Thread(target=self._fyers.connect, daemon=True)
        self._thread.start()

    def disconnect(self):
        self._connected = False
        if hasattr(self._fyers, 'ws') and self._fyers.ws:
            self._fyers.ws.close(status=1000)

    # ── callbacks (run in WS thread) ───────────────────────────

    def _on_open(self):
        self._connected = True
        self._fyers.subscribe(data_type="OnOrders")
        self._fyers.subscribe(data_type="OnPositions")
        self._log.info("Fyers order WS connected")

    def _on_close(self, msg):
        self._connected = False

    def _on_error(self, msg):
        self._log.error(f"Fyers order WS error: {msg}")

    def _on_order(self, msg):
        orders = msg.get("orders") or []
        if not isinstance(orders, list):
            orders = [orders]
        for o in orders:
            self._write_order(o)

    def _on_position(self, msg):
        # positions handled separately if needed
        pass

    def _write_order(self, o: dict):
        ctrl = self._shm.order_ctrl[0]
        widx = int(ctrl['widx'])
        slot = self._shm.orders[widx]

        # ── SEQLOCK WRITER START ──────────────────────────────
        ctrl['seq'] += 1              # odd → "busy"
        # ─────────────────────────────────────────────────────

        slot['status']         = o.get("status", 0)
        slot['order_type']     = o.get("type", 0)
        slot['side']           = o.get("side", 0)
        slot['qty']            = o.get("qty", 0)
        slot['stop_price']     = o.get("stopPrice", 0.0)
        slot['limit_price']    = o.get("limitPrice", 0.0)
        slot['traded_price']   = o.get("tradedPrice", 0.0)
        slot['order_id']       = (o.get("id", "") or "").encode()[:64]
        slot['parent_id']      = (o.get("parentId", "") or "").encode()[:64]
        slot['symbol']         = (o.get("symbol", "") or "").encode()[:32]
        slot['order_datetime'] = o.get("orderDateTime", "").encode()[:32]
        slot['seq']            = int(ctrl['seq'])

        # ── SEQLOCK WRITER END ───────────────────────────────
        ctrl['seq'] += 1              # even → "ready"
        ctrl['widx'] = (widx + 1) % MAX_ORDERS
