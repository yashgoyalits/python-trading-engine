# src/strategies/strike_price_helper.py

from datetime import date, timedelta

_EXCHANGE   = "NSE"
_UNDERLYING = "NIFTY"
_INTERVAL   = 50

_MONTH_ABBR = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}
_WEEKLY_MONTH_CODE = {10: "O", 11: "N", 12: "D"}  # 1-9 use plain digit


def _current_week_expiry(today: date) -> date:
    # Tuesday = weekday 1
    days_to_tuesday = (1 - today.weekday()) % 7
    return today + timedelta(days=days_to_tuesday)


def _is_month_end_expiry(expiry: date) -> bool:
    """True if `expiry` is the LAST Tuesday of its month → monthly contract."""
    return (expiry + timedelta(days=7)).month != expiry.month


def _weekly_month_code(month: int) -> str:
    return _WEEKLY_MONTH_CODE.get(month, str(month))


def atm_strike_price(price: float, side: int) -> str:
    """
    price : nifty spot ltp
    side  : 1 → CE, -1 → PE
    """
    today  = date.today()
    expiry = _current_week_expiry(today)
    strike = round(price / _INTERVAL) * _INTERVAL
    opt    = "CE" if side == 1 else "PE"
    yy     = expiry.strftime("%y")

    if _is_month_end_expiry(expiry):
        exp = yy + _MONTH_ABBR[expiry.month]               # e.g. 26JUN
    else:
        exp = yy + _weekly_month_code(expiry.month) + expiry.strftime("%d")  # e.g. 26630 or 26O04

    return f"{_EXCHANGE}:{_UNDERLYING}{exp}{strike}{opt}"