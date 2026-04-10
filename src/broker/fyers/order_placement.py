import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

_BASE = "https://api-t1.fyers.in"


class FyersOrderPlacement:
    def __init__(self):
        self._client_id    = os.getenv("CLIENT_ID")
        self._access_token = os.getenv("FYERS_ACCESS_TOKEN")
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """Engine start pe call karo — data/order broker ke saath."""
        connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300, ssl=True)
        self._session = aiohttp.ClientSession(
            base_url=_BASE,
            connector=connector,
            headers={"Authorization": f"{self._client_id}:{self._access_token}"},
        )
        try:
            async with self._session.get("/api/v3/profile") as r:
                await r.read()
        except Exception:
            pass  # session ready hai, warmup fail ho toh bhi chalega

    def is_connected(self) -> bool:
        return self._session is not None and not self._session.closed

    async def disconnect(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ── public ────────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        qty: int,
        order_type: int,
        side: int,
        stop_loss: float,
        take_profit: float,
    ) -> dict:
        return await self._post("/api/v3/orders/sync", {
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
        })

    async def modify_order(
        self,
        order_id: str,
        order_type: int,
        limit_price: float,
        stop_price: float,
        qty: int,
    ) -> dict:
        return await self._patch("/api/v3/orders/sync", {
            "id":         order_id,
            "type":       order_type,
            "limitPrice": limit_price,
            "stopPrice":  stop_price,
            "qty":        qty,
        })

    # ── internal ──────────────────────────────────────────────

    async def _post(self, path: str, payload: dict) -> dict:
        async with self._session.post(path, json=payload) as r:
            return await r.json()

    async def _patch(self, path: str, payload: dict) -> dict:
        async with self._session.patch(path, json=payload) as r:
            return await r.json()