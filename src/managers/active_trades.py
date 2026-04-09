from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ACTIVE_TRADES, MAX_TRAILING


class ActiveTradesManager:
    def __init__(self, shm: ShmStore, strategy_id: str):
        self._buf = shm.trades
        self._sid = strategy_id.encode()

    # ── write ops ─────────────────────────────────────────────

    def add_trade(self, trade_no: int, order_id: str):
        slot = self._free_slot()
        if slot is None:
            raise RuntimeError("MAX_ACTIVE_TRADES reached")
        r = self._buf[slot]
        r['active']          = True
        r['trade_no']        = trade_no
        r['strategy_id']     = self._sid
        r['order_id']        = order_id.encode()[:64]
        r['stop_order_id']   = b''
        r['target_order_id'] = b''
        r['symbol']          = b''
        r['qty']             = 0
        r['side']            = 0
        r['entry_price']     = 0.0
        r['stop_price']      = 0.0
        r['target_price']    = 0.0
        r['trailing_count']  = 0
        r['trailing'][:]['hit'] = False

    def update(self, order_id: str, **kwargs):
        r = self._find(order_id)
        if r is None:
            return
        for k, v in kwargs.items():
            if k == 'trailing_levels':
                for i, lvl in enumerate(v[:MAX_TRAILING]):
                    r['trailing'][i]['threshold'] = lvl['threshold']
                    r['trailing'][i]['new_stop']  = lvl['new_stop']
                    r['trailing'][i]['hit']       = lvl.get('hit', False)
                r['trailing_count'] = len(v)
            elif k in ('order_id', 'stop_order_id', 'target_order_id', 'symbol', 'strategy_id'):
                r[k] = (v or '').encode()[:64]
            else:
                r[k] = v

    def close_trade(self, order_id: str):
        r = self._find(order_id)
        if r is not None:
            r['active'] = False

    # ── read ops (return view — zero copy) ────────────────────

    def get_active(self):
        """Returns numpy row view. Caller reads fields directly — no object created."""
        for i in range(MAX_ACTIVE_TRADES):
            if self._buf[i]['active'] and self._buf[i]['strategy_id'] == self._sid:
                return self._buf[i]
        return None

    # ── internal ──────────────────────────────────────────────

    def _find(self, order_id: str):
        oid = order_id.encode()
        for i in range(MAX_ACTIVE_TRADES):
            if self._buf[i]['active'] and self._buf[i]['order_id'] == oid:
                return self._buf[i]
        return None

    def _free_slot(self):
        for i in range(MAX_ACTIVE_TRADES):
            if not self._buf[i]['active']:
                return i
        return None
