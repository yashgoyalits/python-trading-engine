# src/error_handling/policies.py
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_delay:   float   # tenacity wait_exponential_jitter ka `initial`
    max_delay:    float   # tenacity wait_exponential_jitter ka `max` (cap)


# ── Order placement ──────────────────────────────────────────────
# Kam retries — idempotency risk hai: agar request broker tak pahunch gaya tha
# aur sirf response timeout hua, retry duplicate order bana sakta hai.
ORDER_PLACEMENT_POLICY = RetryPolicy(max_attempts=2, base_delay=1.0, max_delay=3.0)

# ── Order modify/cancel ───────────────────────────────────────────
# Duplicate-order risk yaha nahi hai (existing order ko hi modify kar rahe hai),
# thoda zyada patient ho sakte hai.
ORDER_MODIFY_POLICY = RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=5.0)

# ── REST client startup handshake (profile-check) ────────────────
REST_CONNECT_POLICY = RetryPolicy(max_attempts=3, base_delay=2.0, max_delay=10.0)

# ── WebSocket reconnect (data socket + order socket) ──────────────
# Bina WS connection bot trade hi nahi kar sakta — bahut patient rakho.
WS_RECONNECT_POLICY = RetryPolicy(max_attempts=15, base_delay=2.0, max_delay=30.0)
