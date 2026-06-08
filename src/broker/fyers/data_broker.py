# src/broker/fyers/data_broker.py
# CHANGE: SymbolRegistry → SymbolManager (get() method same hai)
import os
import asyncio
import threading
from dotenv import load_dotenv
from src.logger import log
from fyers_apiv3.FyersWebsocket import data_ws
from src.core.shm_store import ShmStore
from src.symbol_manager.symbol_manager import SymbolManager
from src.core.dtypes import *

load_dotenv()

class FyersDataBroker:
    def __init__(self, shm: ShmStore, symbols: SymbolManager):
        self._shm     = shm
        self._symbols = symbols          # get() method use hota hai — interface same
        self._token   = os.getenv("FYERS_ACCESS_TOKEN")
        self._socket  = None
        self._thread  = None
        self._loop    = None
        self._running = False
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def connect(self, loop: asyncio.AbstractEventLoop):
        self._loop    = loop
        self._running = True
        self._thread  = threading.Thread(target=self._run_ws, daemon=True)
        self._thread.start()

    def subscribe(self, symbols: list[str]):
        if self._socket and self._connected:
            self._socket.subscribe(symbols, "SymbolUpdate")

    def unsubscribe(self, symbols: list[str]):
        if self._socket and self._connected:
            self._socket.unsubscribe(symbols)

    def disconnect(self):
        self._running = False
        self._connected = False
        if self._socket:
            self._socket.close_connection()

    # ── internal ──────────────────────────────────────────────

    def _run_ws(self):
        def _on_open():
            self._connected = True
            syms = list(self._symbols.all_symbols().keys())
            if syms:
                self._socket.subscribe(syms, "SymbolUpdate")
            log.info(f"Fyers data WS connected — {len(syms)} symbols re-subscribed")

        def _on_close(msg):
            self._connected = False
            log.info(f"Fyers data WS closed: {msg}")

        def _on_error(err):
            log.error(f"Fyers data WS error: {err}")

        def _on_message(msg):
            if msg.get("type") not in ("if", "sf"):
                return
            sym = msg.get("symbol")
            idx = self._symbols.get(sym)   # SymbolManager.get() — same as before
            if idx is None:
                return
            self._write_tick(idx, msg)

        self._socket = data_ws.FyersDataSocket(
            access_token=self._token,
            reconnect=True,
            litemode=False,
            write_to_file=False,
            log_path=None,
            on_connect=_on_open,
            on_message=_on_message,
            on_error=_on_error,
            on_close=_on_close,
        )
        self._socket.connect()
        self._socket.keep_running()

    def _write_tick(self, sym_idx: int, msg: dict):
        ctrl = self._shm.ctrl[sym_idx]
        widx = int(ctrl['tick_widx'])
        slot = self._shm.ticks[sym_idx * MAX_TICKS_PER_SYMBOL + widx]

        ctrl['tick_seq'] += 1
        slot['timestamp']  = msg.get("exch_feed_time", 0)
        slot['ltp']        = msg.get("ltp", 0.0)
        slot['volume']     = msg.get("volume", 0)
        slot['open_price'] = msg.get("open_price", 0.0)
        slot['high_price'] = msg.get("high_price", 0.0)
        slot['low_price']  = msg.get("low_price", 0.0)
        slot['prev_close'] = msg.get("prev_close_price", 0.0)
        ctrl['tick_seq'] += 1
        ctrl['tick_widx'] = (widx + 1) % MAX_TICKS_PER_SYMBOL