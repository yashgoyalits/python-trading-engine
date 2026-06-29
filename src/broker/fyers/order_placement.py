import os
import httpx
from src.logger import log
from src.error_handling.retry import with_retry
from src.error_handling.policies import (
    ORDER_PLACEMENT_POLICY, ORDER_MODIFY_POLICY, REST_CONNECT_POLICY,
)

_BASE = "https://api-t1.fyers.in"

class FyersOrderPlacement:
    def __init__(self):
        self._client_id    = os.getenv("CLIENT_ID")
        self._access_token = os.getenv("FYERS_ACCESS_TOKEN")
        self._client: httpx.AsyncClient | None = None
        self._connected = False

    @with_retry(REST_CONNECT_POLICY, label="FyersOrderPlacement.connect")
    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE,
            http2=True,
            headers={"Authorization": f"{self._client_id}:{self._access_token}"},
            timeout=httpx.Timeout(5.0),
        )
        try:
            r = await self._client.get("/api/v3/profile")
            r.raise_for_status()                      # ← status code ab check hota hai
            data = r.json()
            if data.get("s") != "ok":
                raise RuntimeError(f"Fyers auth check failed: {data}")
            self._connected = True
        except Exception as e:
            self._connected = False
            await self._client.aclose()
            self._client = None
            log.error(f"FyersOrderPlacement.connect failed: {e}")   # ← log ab imported hai
            raise

    def is_connected(self) -> bool:
        return self._connected

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def place_order(self, symbol, qty, order_type, side, stop_loss, take_profit) -> dict:
        payload = {
            "symbol":       symbol,
            "qty":          qty,
            "type":         order_type,
            "side":         side,
            "productType":  "BO",
            "validity":     "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "stopLoss":     stop_loss,
            "takeProfit":   take_profit,
        }
        try:
            return await self._post("/api/v3/orders/sync", payload)
        except Exception as e:
            # retry exhaust ho gaya ya non-retryable fail hua — dono cases mein
            # existing contract preserve karo: StrategyHandler `res.get('code')`
            # check karta hai, isliye exception bubble nahi hone deni.
            log.error(f"FyersOrderPlacement.place_order failed: {e}")
            return {"code": -1, "message": str(e)}

    async def modify_order(self, order_id, order_type, limit_price, stop_price, qty) -> dict:
        payload = {
            "id":         order_id,
            "type":       order_type,
            "limitPrice": limit_price,
            "stopPrice":  stop_price,
            "qty":        qty,
        }
        try:
            return await self._patch("/api/v3/orders/sync", payload)
        except Exception as e:
            log.error(f"FyersOrderPlacement.modify_order failed: {e}")
            return {"code": -1, "message": str(e)}

    # ── order placement: kam retries (idempotency risk) ──────────
    @with_retry(ORDER_PLACEMENT_POLICY, label="FyersOrderPlacement._post")
    async def _post(self, path: str, payload: dict) -> dict:
        r = await self._client.post(path, json=payload)
        r.raise_for_status()
        return r.json()

    # ── order modify/cancel: zyada retries theek hai ──────────────
    @with_retry(ORDER_MODIFY_POLICY, label="FyersOrderPlacement._patch")
    async def _patch(self, path: str, payload: dict) -> dict:
        r = await self._client.patch(path, json=payload)
        r.raise_for_status()
        return r.json()