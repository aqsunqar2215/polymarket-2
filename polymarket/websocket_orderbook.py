from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable

import structlog
import websockets

logger = structlog.get_logger(__name__)


class OrderbookSnapshot:
    """Снимок стакана в момент времени"""

    def __init__(
        self,
        token_id: str,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        timestamp: float,
    ):
        self.token_id = token_id
        self.bids = bids  # [(price, size), ...]
        self.asks = asks
        self.timestamp = timestamp
        self.best_bid = bids[0][0] if bids else 0.0
        self.best_ask = asks[0][0] if asks else 1.0
        self.spread_bps = (
            int((self.best_ask - self.best_bid) / ((self.best_bid + self.best_ask) / 2) * 10000)
            if self.best_ask > self.best_bid > 0
            else 0
        )

    def is_valid(self) -> bool:
        """Проверить, валиден ли стакан"""
        return bool(self.bids and self.asks and 0 < self.best_bid < self.best_ask < 1)


class PolymarketWebSocketOrderbook:
    """
    Real-time L2 orderbook WebSocket client для Polymarket CLOB.
    
    Поддерживает:
    - Подписку на несколько токенов одновременно
    - Автоматическое переподключение при разрыве
    - Кэширование последних snapshots
    - Callbacks при обновлении стакана
    """

    def __init__(self, ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws"):
        self.ws_url = ws_url
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.running = False
        
        # Хранение стаканов по token_id
        self._orderbook_cache: dict[str, OrderbookSnapshot] = {}
        self._cache_lock = asyncio.Lock()
        
        # Callbacks при обновлении
        self._update_callbacks: list[Callable[[str, OrderbookSnapshot], Any]] = []
        
        # Статистика
        self._messages_received = 0
        self._updates_processed = 0
        self._connection_attempts = 0
        self._last_message_time = time.time()
        self._subscribed_tokens: set[str] = set()

    def register_callback(self, callback: Callable[[str, OrderbookSnapshot], Any]) -> None:
        """Зарегистрировать callback для обновлений стакана"""
        self._update_callbacks.append(callback)
        logger.info("callback_registered", callback_name=callback.__name__)

    async def connect(self) -> bool:
        """Подключиться к WebSocket"""
        self._connection_attempts += 1
        
        try:
            logger.info(
                "websocket_connecting",
                url=self.ws_url,
                attempt=self._connection_attempts,
            )
            
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=20,  # Ping каждые 20 сек
                ping_timeout=10,
                close_timeout=10,
            )
            
            logger.info("websocket_connected", url=self.ws_url)
            self.running = True
            return True
            
        except Exception as e:
            logger.error(
                "websocket_connection_failed",
                error=str(e),
                attempt=self._connection_attempts,
            )
            self.running = False
            return False

    async def subscribe(self, token_id: str) -> bool:
        """Подписаться на обновления стакана для токена"""
        if not self.websocket:
            logger.warning("websocket_not_connected", token_id=token_id)
            return False
        
        if token_id in self._subscribed_tokens:
            logger.debug("already_subscribed", token_id=token_id)
            return True
        
        try:
            # Polymarket WebSocket format for orderbook subscription
            message = {
                "type": "subscribe",
                "channel": "orderbook",
                "token_id": token_id,
            }
            
            await self.websocket.send(json.dumps(message))
            self._subscribed_tokens.add(token_id)
            
            logger.info("subscribed_to_orderbook", token_id=token_id)
            return True
            
        except Exception as e:
            logger.error("subscription_failed", token_id=token_id, error=str(e))
            return False

    async def subscribe_multiple(self, token_ids: list[str]) -> int:
        """Подписаться на несколько токенов"""
        success_count = 0
        
        for token_id in token_ids:
            if await self.subscribe(token_id):
                success_count += 1
            await asyncio.sleep(0.01)  # Rate limiting
        
        logger.info(
            "subscribed_to_multiple",
            requested=len(token_ids),
            success=success_count,
        )
        return success_count

    def _parse_orderbook_message(self, data: dict[str, Any]) -> OrderbookSnapshot | None:
        """Распарсить сообщение о стакане"""
        try:
            token_id = data.get("token_id") or data.get("tokenId")
            
            if not token_id:
                logger.debug("message_missing_token_id", data_keys=list(data.keys()))
                return None
            
            # Parse bids
            bids_raw = data.get("bids", [])
            bids = []
            for bid in bids_raw:
                if isinstance(bid, (list, tuple)) and len(bid) >= 2:
                    try:
                        price = float(bid[0])
                        size = float(bid[1])
                        if 0 <= price <= 1 and size > 0:
                            bids.append((price, size))
                    except (ValueError, TypeError):
                        continue
            
            # Parse asks
            asks_raw = data.get("asks", [])
            asks = []
            for ask in asks_raw:
                if isinstance(ask, (list, tuple)) and len(ask) >= 2:
                    try:
                        price = float(ask[0])
                        size = float(ask[1])
                        if 0 <= price <= 1 and size > 0:
                            asks.append((price, size))
                    except (ValueError, TypeError):
                        continue
            
            if not bids or not asks:
                logger.debug(
                    "empty_orderbook_from_ws",
                    token_id=token_id,
                    bid_count=len(bids),
                    ask_count=len(asks),
                )
                return None
            
            snapshot = OrderbookSnapshot(
                token_id=token_id,
                bids=bids,
                asks=asks,
                timestamp=time.time(),
            )
            
            if snapshot.is_valid():
                return snapshot
            
            logger.debug(
                "invalid_orderbook_snapshot",
                token_id=token_id,
                best_bid=snapshot.best_bid,
                best_ask=snapshot.best_ask,
            )
            return None
            
        except Exception as e:
            logger.debug("orderbook_parsing_failed", error=str(e))
            return None

    async def _process_message(self, message: str) -> None:
        """Обработать сообщение от WebSocket"""
        try:
            data = json.loads(message)
            self._messages_received += 1
            self._last_message_time = time.time()
            
            # Handle orderbook updates
            if data.get("type") == "orderbook" or "bids" in data:
                snapshot = self._parse_orderbook_message(data)
                
                if snapshot:
                    self._updates_processed += 1
                    
                    # Update cache
                    async with self._cache_lock:
                        self._orderbook_cache[snapshot.token_id] = snapshot
                    
                    # Log update
                    logger.debug(
                        "orderbook_updated",
                        token_id=snapshot.token_id[:16],
                        best_bid=round(snapshot.best_bid, 6),
                        best_ask=round(snapshot.best_ask, 6),
                        spread_bps=snapshot.spread_bps,
                        bid_levels=len(snapshot.bids),
                        ask_levels=len(snapshot.asks),
                    )
                    
                    # Trigger callbacks
                    for callback in self._update_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(snapshot.token_id, snapshot)
                            else:
                                callback(snapshot.token_id, snapshot)
                        except Exception as e:
                            logger.error("callback_error", error=str(e))
        
        except json.JSONDecodeError:
            logger.debug("invalid_json_message")
        except Exception as e:
            logger.error("message_processing_failed", error=str(e))

    async def listen(self) -> None:
        """Основной цикл прослушивания WebSocket"""
        while self.running:
            try:
                if not self.websocket:
                    if not await self.connect():
                        await asyncio.sleep(5)
                        continue
                
                message = await asyncio.wait_for(
                    self.websocket.recv(),
                    timeout=30.0,
                )
                
                await self._process_message(message)
                
            except asyncio.TimeoutError:
                logger.warning("websocket_timeout")
                await self.reconnect()
            except websockets.exceptions.ConnectionClosed:
                logger.warning("websocket_connection_closed")
                await self.reconnect()
            except Exception as e:
                logger.error("listen_error", error=str(e))
                await asyncio.sleep(2)

    async def reconnect(self) -> None:
        """Переподключиться к WebSocket"""
        logger.info("reconnecting_websocket")
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
        
        self.websocket = None
        await asyncio.sleep(2)
        
        if await self.connect():
            # Переподписаться на все токены
            for token_id in list(self._subscribed_tokens):
                await self.subscribe(token_id)

    async def get_orderbook(self, token_id: str) -> OrderbookSnapshot | None:
        """Получить последний snapshot стакана"""
        async with self._cache_lock:
            return self._orderbook_cache.get(token_id)

    async def get_multiple_orderbooks(
        self,
        token_ids: list[str],
    ) -> dict[str, OrderbookSnapshot | None]:
        """Получить snapshots для нескольких токенов"""
        async with self._cache_lock:
            return {
                token_id: self._orderbook_cache.get(token_id)
                for token_id in token_ids
            }

    def get_statistics(self) -> dict[str, Any]:
        """Получить статистику WebSocket клиента"""
        uptime_seconds = time.time() - self._last_message_time if self._messages_received > 0 else 0
        
        return {
            "connected": bool(self.websocket),
            "running": self.running,
            "subscribed_tokens": len(self._subscribed_tokens),
            "cached_orderbooks": len(self._orderbook_cache),
            "messages_received": self._messages_received,
            "updates_processed": self._updates_processed,
            "connection_attempts": self._connection_attempts,
            "last_message_ago_seconds": round(time.time() - self._last_message_time, 1),
            "processing_rate": (
                round(self._updates_processed / max(uptime_seconds, 1), 2)
                if self._messages_received > 0
                else 0
            ),
        }

    async def close(self) -> None:
        """Закрыть WebSocket соединение"""
        logger.info("closing_websocket")
        self.running = False
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error("websocket_close_error", error=str(e))
        
        self.websocket = None