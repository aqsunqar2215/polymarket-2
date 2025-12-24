from __future__ import annotations
from typing import Any
import httpx
import structlog
from src.config import Settings

logger = structlog.get_logger(__name__)

class PolymarketRestClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.polymarket_api_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def get_market_info(self, market_id: str) -> dict[str, Any]:
        response = await self.client.get(f"{self.base_url}/markets/{market_id}")
        response.raise_for_status()
        return response.json()

    async def get_orderbook(self, market_id: str) -> dict[str, Any]:
        try:
            data = await self.get_market_info(market_id)
            return {
                "best_bid": float(data.get("bestBid", 0)),
                "best_ask": float(data.get("bestAsk", 1)),
                "market_id": market_id
            }
        except Exception as e:
            logger.error("gamma_orderbook_failed", market_id=market_id, error=str(e))
            return {"best_bid": 0.0, "best_ask": 1.0}

    async def close(self):
        await self.client.aclose()