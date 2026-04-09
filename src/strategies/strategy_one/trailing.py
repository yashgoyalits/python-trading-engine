from src.managers.active_trades import ActiveTradesManager
from src.managers.order_placement_manager import FyersOrderPlacement
from src.infrastructure.logger import ShmLogger


class TrailingManager:
    def __init__(self, trades: ActiveTradesManager, placement: FyersOrderPlacement, logger: ShmLogger):
        self._trades   = trades
        self._place    = placement
        self._log      = logger

    async def check(self, tick_view, trade_view):
        """tick_view, trade_view are direct numpy row views — zero copy."""
        if not trade_view['active']:
            return

        ltp   = float(tick_view['ltp'])
        count = int(trade_view['trailing_count'])
        if count == 0:
            return

        stop_oid = trade_view['stop_order_id'].decode().rstrip('\x00')
        qty      = int(trade_view['qty'])
        order_id = trade_view['order_id'].decode().rstrip('\x00')

        for i in range(count):
            lvl = trade_view['trailing'][i]
            if lvl['hit']:
                continue
            if ltp > lvl['threshold']:
                res = await self._place.modify_order(
                    stop_oid,
                    order_type=4,
                    limit_price=float(lvl['new_stop']),
                    stop_price=float(lvl['new_stop']),
                    qty=qty,
                )
                if res.get('code') == 1102:
                    # Write hit flag directly into SHM
                    trade_view['trailing'][i]['hit'] = True
                    self._log.info(f"Trailing SL hit level {i} | LTP {ltp}")
                else:
                    self._log.error(f"Trailing SL modify failed: {res}")
