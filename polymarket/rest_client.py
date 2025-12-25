from __future__ import annotations

import time
import asyncio
from typing import Any

import httpx
import structlog
from py_clob_client.client import ClobClient
# В новых версиях используются ApiCreds вместо ApiCredential
from py_clob_client.clob_types import ApiCreds, OrderArgs
from py_clob_client.constants import POLYGON

from src.config import Settings

logger = structlog.get_logger(__name__)


class PolymarketRestClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.polymarket_api_url
        self.clob_url = settings.polymarket_clob_url
        self.client = httpx.AsyncClient(timeout=30.0)

        # Инициализация официального CLOB клиента
        self.clob_client = self._init_clob_client()

        # Кэширование Gamma API данных
        self._market_info_cache: dict[str, dict[str, Any]] = {}
        self._market_cache_time: dict[str, float] = {}
        self._cache_ttl_seconds = 5.0

        # Статистика
        self._l2_fetch_count = 0
        self._l2_success_count = 0
        self._l2_empty_count = 0
        self._l2_error_count = 0
        self._gamma_cache_hits = 0
        self._gamma_cache_misses = 0

    def _init_clob_client(self) -> ClobClient:
        """Инициализация торгового клиента с авторизацией L2"""
        try:
            # Создаем объект учетных данных (используем ApiCreds)
            creds = ApiCreds(
                api_key=self.settings.polymarket_api_key,
                api_secret=self.settings.polymarket_api_secret,
                api_passphrase=self.settings.polymarket_api_passphrase,
            )

            # Инициализируем клиент.
            # Обратите внимание: в новых версиях creds передаются через метод или при создании
            client = ClobClient(
                self.clob_url,
                key=self.settings.private_key,
                chain_id=POLYGON,
                creds=creds
            )
            return client
        except Exception as e:
            logger.error("clob_client_init_failed", error=str(e))
            return None

    # --- ТОРГОВЫЕ МЕТОДЫ ---

    async def cancel_all_orders(self, market_id: str = None):
        """Отменяет все ордера аккаунта"""
        if not self.clob_client:
            return

        try:
            loop = asyncio.get_event_loop()
            # Используем официальный метод cancel_all()
            resp = await loop.run_in_executor(None, self.clob_client.cancel_all)
            logger.info("all_orders_cancelled", response=resp)
            return resp
        except Exception as e:
            logger.error("cancel_all_failed", error=str(e))
            return None

    async def create_order(self, quote: dict[str, Any]):
        """Создание ордера с флагом POST_ONLY"""
        if not self.clob_client:
            return None

        try:
            order_args = OrderArgs(
                price=float(quote["price"]),
                size=float(quote["size"]),
                side=quote["side"],
                token_id=quote["token_id"]
            )

            loop = asyncio.get_event_loop()
            # post_only=True критически важен для Spread Farming (Maker Rebates)
            resp = await loop.run_in_executor(
                None,
                lambda: self.clob_client.create_order(order_args, post_only=True)
            )

            logger.info("order_placed",
                        side=quote["side"],
                        price=quote["price"],
                        size=quote["size"])
            return resp
        except Exception as e:
            logger.error("create_order_failed", error=str(e))
            return None

    # --- МЕТОДЫ ЧТЕНИЯ (ОСТАВЛЯЕМ БЕЗ ИЗМЕНЕНИЙ) ---

    async def get_market_info(self, market_id: str) -> dict[str, Any]:
        age = time.time() - self._market_cache_time.get(market_id, 0)
        if market_id in self._market_info_cache and age < self._cache_ttl_seconds:
            self._gamma_cache_hits += 1
            return self._market_info_cache[market_id]

        self._gamma_cache_misses += 1
        response = await self.client.get(f"{self.base_url}/markets/{market_id}")
        response.raise_for_status()
        data = response.json()
        self._market_info_cache[market_id] = data
        self._market_cache_time[market_id] = time.time()
        return data

    async def get_l2_orderbook(self, token_id: str) -> dict[str, Any] | None:
        self._l2_fetch_count += 1
        try:
            response = await self.client.get(f"{self.clob_url}/book", params={"token_id": token_id})
            data = response.json()
            bids = [(float(b[0]), float(b[1])) for b in data.get("bids", [])]
            asks = [(float(a[0]), float(a[1])) for a in data.get("asks", [])]
            if not bids or not asks: return None
            self._l2_success_count += 1
            return {"bids": bids, "asks": asks, "token_id": token_id, "success": True}
        except Exception:
            self._l2_error_count += 1
            return None

    async def get_orderbook(self, market_id: str, token_ids: list[str] | None = None) -> dict[str, Any]:
        gamma_data = await self.get_market_info(market_id)
        best_bid = float(gamma_data.get("bestBid", 0))
        best_ask = float(gamma_data.get("bestAsk", 1))
        l2_available = False
        l2_data = None

        if token_ids and len(token_ids) >= 2:
            yes_l2 = await self.get_l2_orderbook(token_ids[0])
            if yes_l2:
                best_bid, best_ask = yes_l2["bids"][0][0], yes_l2["asks"][0][0]
                l2_available = True
                l2_data = {"yes": yes_l2, "no": await self.get_l2_orderbook(token_ids[1])}

        return {
            "market_id": market_id,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "l2_data": l2_data,
            "l2_available": l2_available,
            "token_ids": token_ids or []
        }

    async def close(self):
        await self.client.aclose()