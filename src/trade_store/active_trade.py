from src.core.shm_store import ShmStore
from src.core.dtypes import MAX_TRAILING


class ActiveTradesManager:
    def __init__(
        self,
        shm: ShmStore,
        strategy_id: str,
        slot_start: int,
    ):
        self._slot = slot_start
        self._buf  = shm.trades
        self._sid  = strategy_id.encode()

    # ── write ops ─────────────────────────────────────────────

    def add_trade(self, trade_no: int, order_id: str) -> None:
        r = self._buf[self._slot]
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

    def update(self, order_id: str, **kwargs) -> None:
        r = self._buf[self._slot]

        if not r['active']:
            return

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
        self._buf[self._slot]['active'] = False

    def mark_trailing_hit(self, order_id: str, level_idx: int) -> None:
        self._buf[self._slot]['trailing'][level_idx]['hit'] = True

    # ── read ops ──────────────────────────────────────────────

    def get_active(self):
        r = self._buf[self._slot]

        if not r['active']:
            return None

        if r['strategy_id'].tobytes().rstrip(b'\x00') != self._sid.rstrip(b'\x00'):
            return None

        return r

    def has_active(self) -> bool:
        return self.get_active() is not None