# src/strategies/strike_price_helper.py

from datetime import date, timedelta

_EXCHANGE = "NSE"
_UNDERLYING = "NIFTY"
_INTERVAL = 50


def _current_week_expiry(today: date) -> date:
    # Tuesday = weekday 1
    days_to_tuesday = (1 - today.weekday()) % 7
    return today + timedelta(days=days_to_tuesday)


def atm_strike_price(price: float, side: int) -> str:
    """
    price : nifty spot ltp
    side  : 1 → CE, -1 → PE
    """
    today  = date.today()
    expiry = _current_week_expiry(today)
    strike = round(price / _INTERVAL) * _INTERVAL
    opt    = "CE" if side == 1 else "PE"
    exp = expiry.strftime("%y") + str(expiry.month) + expiry.strftime("%d")   # 260609
    return f"{_EXCHANGE}:{_UNDERLYING}{exp}{strike}{opt}"