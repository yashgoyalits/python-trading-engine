from collections import deque
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_ACTIVE_TRADES, MAX_TRAILING

class ActiveTradesManager:
    def __init__(self, shm: ShmStore, strategy_id: str):
        self._buf = shm.trades
        self._sid = strategy_id.encode()

        # ── in-process indexes (O(1) lookup) ──────────────────
        self._free: deque[int] = deque(range(MAX_ACTIVE_TRADES))  # free slot pool
        self._idx:  dict[str, int] = {}   # order_id → slot index
        self._active_slot: int | None = None  # cached active slot for this strategy

    # ── write ops ─────────────────────────────────────────────

    def add_trade(self, trade_no: int, order_id: str):
        if not self._free:
            raise RuntimeError("MAX_ACTIVE_TRADES reached")

        slot_i = self._free.popleft()           # O(1)
        r = self._buf[slot_i]
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

        self._idx[order_id]  = slot_i           # register in index
        self._active_slot    = slot_i           # cache it

    def update(self, order_id: str, **kwargs):
        slot_i = self._idx.get(order_id)
        if slot_i is None:
            return
        r = self._buf[slot_i]

        for k, v in kwargs.items():

            if k == 'trailing_levels':
                for i, lvl in enumerate(v[:MAX_TRAILING]):
                    r['trailing'][i]['threshold'] = lvl['threshold']
                    r['trailing'][i]['new_stop']  = lvl['new_stop']
                    r['trailing'][i]['hit']       = lvl.get('hit', False)
                r['trailing_count'] = len(v)

            elif k in ('stop_order_id', 'target_order_id'):
                r[k] = v.encode()[:64]

            elif k in ('symbol', 'strategy_id'):
                r[k] = v.encode()[:32]

            else:
                r[k] = v

    def close_trade(self, order_id: str):
        slot_i = self._idx.pop(order_id, None)  # O(1)
        if slot_i is None:
            return
        self._buf[slot_i]['active'] = False
        self._free.append(slot_i)               # slot wapas pool mein
        self._active_slot = None

    # ── read ops ──────────────────────────────────────────────

    def get_active(self):
        """O(1) — cached slot, no loop, no decode."""
        if self._active_slot is None:
            return None
        row = self._buf[self._active_slot]
        if row['active']:
            return row
        # stale cache (e.g. external close) — invalidate
        self._active_slot = None
        return None

    # ── internal ──────────────────────────────────────────────

    def _get_by_id(self, order_id: str):
        """O(1) dict lookup instead of O(n) loop."""
        slot_i = self._idx.get(order_id)
        if slot_i is None:
            return None
        return self._buf[slot_i]