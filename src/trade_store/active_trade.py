from collections import deque
from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TRAILING


class ActiveTradesManager:
    def __init__(
        self,
        shm: ShmStore,
        strategy_id: str,
        slot_start: int,
        slot_count: int,
    ):
        self._buf  = shm.trades
        self._sid  = strategy_id.encode()

        self._free: deque[int] = deque(range(slot_start, slot_start + slot_count))
        self._idx:  dict[str, int] = {}
        self._active_slot: int | None = None

    # ── write ops ─────────────────────────────────────────────

    def add_trade(self, trade_no: int, order_id: str) -> None:
        if not self._free:
            raise RuntimeError("slot_count exhausted for this strategy")

        slot_i = self._free.popleft()
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

        self._idx[order_id] = slot_i
        self._active_slot   = slot_i

    def update(self, order_id: str, **kwargs) -> None:
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

            elif k in ('stop_order_id', 'target_order_id', 'order_id'):
                r[k] = v.encode()[:64]

            elif k in ('symbol', 'strategy_id'):
                r[k] = v.encode()[:32]

            else:
                r[k] = v

    def close_trade(self, order_id: str) -> None:
        slot_i = self._idx.pop(order_id, None)
        if slot_i is None:
            return
        self._buf[slot_i]['active'] = False
        self._free.append(slot_i)
        self._active_slot = None

    def mark_trailing_hit(self, order_id: str, level_idx: int) -> None:
        slot_i = self._idx.get(order_id)
        if slot_i is None:
            return
        self._buf[slot_i]['trailing'][level_idx]['hit'] = True

    # ── read ops ──────────────────────────────────────────────

    def get_active(self):
        if self._active_slot is None:
            return None

        slot_i = self._active_slot
        row    = self._buf[slot_i]

        if not row['active']:
            self._active_slot = None
            return None

        if row['strategy_id'].tobytes().rstrip(b'\x00') != self._sid.rstrip(b'\x00'):
            self._active_slot = None
            return None

        oid = row['order_id'].tobytes().rstrip(b'\x00').decode()
        if self._idx.get(oid) != slot_i:
            self._active_slot = None
            return None

        return row

    def has_active(self) -> bool:
        return self.get_active() is not None