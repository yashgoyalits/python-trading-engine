# src/error_handling/exceptions.py
import httpx


class TradingError(Exception):
    """Base class — error_handling module ke sab custom exceptions isi se aate hai."""


class RetryableError(TradingError):
    """Transient failure — retry karna safe hai."""


class NonRetryableError(TradingError):
    """Permanent failure — retry se kuch nahi hoga, fail fast karo."""


class BrokerConnectionError(RetryableError):
    """WebSocket ya REST connection drop ho gaya ya establish nahi ho paya."""


class AuthenticationError(NonRetryableError):
    """Token/credentials invalid ya expired — yaha insaan ko fix karna padega, retry nahi."""


class OrderPlacementError(TradingError):
    """Order placement fail hua — retryable ya nahi, classify_exception() decide karta hai."""


class OrderModificationError(TradingError):
    """Order modify/cancel fail hua."""


class ReconnectFailedError(TradingError):
    """Ek reconnect attempt ke baad bhi broker connected nahi hua — tenacity ko retry signal."""


# 4xx mein se kewal yeh retryable hai (rate-limit/timeout-jaisa); baaki 4xx = client ki
# galti, retry se theek nahi hoga.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def classify_exception(exc: Exception) -> bool:
    """
    tenacity ka retry_if_exception() predicate — isi se decide hota hai retry
    karna hai ya turant fail fast karna hai.

    True  -> retryable (timeout, connection drop, 5xx, 429)
    False -> non-retryable (bad request, auth failure, anjaan exception)
    """
    if isinstance(exc, NonRetryableError):
        return False
    if isinstance(exc, RetryableError):
        return True

    if isinstance(exc, (
        httpx.ConnectError, httpx.ConnectTimeout,
        httpx.ReadTimeout, httpx.WriteTimeout,
        httpx.PoolTimeout, httpx.RemoteProtocolError,
    )):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS

    # Anjaan exception type — andhe retry se behtar fail fast karna hai
    return False
