from __future__ import annotations

import time
from typing import Any
import structlog
from dataclasses import dataclass

from src.execution.order_executor import OrderExecutor
from src.market_maker.quote_engine import Quote

logger = structlog.get_logger(__name__)


@dataclass
class ActiveOrder:
    """Активный ордер"""
    order_id: str
    side: str
    price: float
    size: float
    token_id: str
    placed_at: float
    expires_at: float


class OrderPlacer:
    """Размещает ордера из котировок"""
    
    def __init__(self, order_executor: OrderExecutor, order_lifetime_ms: int = 3000):
        self.executor = order_executor
        self.order_lifetime_ms = order_lifetime_ms
        self.active_orders: dict[str, ActiveOrder] = {}
    
    async def place_quotes(
        self,
        market_id: str,
        yes_quote: Quote | None,
        no_quote: Quote | None,
    ) -> tuple[str | None, str | None]:
        """
        Размещает YES и NO котировки.
        Возвращает: (yes_order_id, no_order_id)
        """
        yes_order_id = None
        no_order_id = None
        
        # Размещаем YES ордер
        if yes_quote:
            try:
                yes_order = {
                    "market": market_id,
                    "side": yes_quote.side,
                    "price": yes_quote.price,
                    "size": yes_quote.size,
                    "tokenId": yes_quote.token_id,
                }
                
                result = await self.executor.place_order(yes_order)
                yes_order_id = result.get("id")
                
                if yes_order_id:
                    self.active_orders[yes_order_id] = ActiveOrder(
                        order_id=yes_order_id,
                        side=yes_quote.side,
                        price=yes_quote.price,
                        size=yes_quote.size,
                        token_id=yes_quote.token_id,
                        placed_at=time.time(),
                        expires_at=time.time() + (self.order_lifetime_ms / 1000.0),
                    )
                    logger.info(
                        "order_placed_yes",
                        order_id=yes_order_id,
                        price=round(yes_quote.price, 6),
                        size=round(yes_quote.size, 2),
                    )
            except Exception as e:
                logger.error("yes_order_placement_failed", error=str(e))
        
        # Размещаем NO ордер
        if no_quote:
            try:
                no_order = {
                    "market": market_id,
                    "side": no_quote.side,
                    "price": no_quote.price,
                    "size": no_quote.size,
                    "tokenId": no_quote.token_id,
                }
                
                result = await self.executor.place_order(no_order)
                no_order_id = result.get("id")
                
                if no_order_id:
                    self.active_orders[no_order_id] = ActiveOrder(
                        order_id=no_order_id,
                        side=no_quote.side,
                        price=no_quote.price,
                        size=no_quote.size,
                        token_id=no_quote.token_id,
                        placed_at=time.time(),
                        expires_at=time.time() + (self.order_lifetime_ms / 1000.0),
                    )
                    logger.info(
                        "order_placed_no",
                        order_id=no_order_id,
                        price=round(no_quote.price, 6),
                        size=round(no_quote.size, 2),
                    )
            except Exception as e:
                logger.error("no_order_placement_failed", error=str(e))
        
        return (yes_order_id, no_order_id)
    
    async def cancel_expired_orders(self) -> int:
        """Отменяет ордера с истекшим сроком"""
        now = time.time()
        expired = [
            oid for oid, order in self.active_orders.items()
            if now > order.expires_at
        ]
        
        for order_id in expired:
            try:
                await self.executor.cancel_order(order_id)
                del self.active_orders[order_id]
                logger.info("expired_order_cancelled", order_id=order_id)
            except Exception as e:
                logger.error("failed_to_cancel_expired_order", order_id=order_id, error=str(e))
        
        return len(expired)
    
    async def cancel_all(self) -> int:
        """Отменяет все активные ордера"""
        order_ids = list(self.active_orders.keys())
        
        if not order_ids:
            return 0
        
        cancelled = await self.executor.batch_cancel_orders(order_ids)
        self.active_orders.clear()
        
        logger.info("all_orders_cancelled", count=cancelled)
        return cancelled