from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class OrderFill:
    """Информация о заполненном ордере"""
    order_id: str
    token_id: str
    side: str
    filled_size: float
    filled_price: float
    timestamp: float


class FillTracker:
    """Отслеживает заполнения и обновляет инвентарь"""
    
    def __init__(self):
        self.fills: dict[str, OrderFill] = {}
    
    def record_fill(self, fill_data: dict[str, Any]) -> OrderFill | None:
        """Записывает заполнение ордера из WebSocket или API"""
        try:
            order_id = fill_data.get("id")
            if not order_id:
                return None
            
            fill = OrderFill(
                order_id=order_id,
                token_id=fill_data.get("tokenId", ""),
                side=fill_data.get("side", ""),
                filled_size=float(fill_data.get("filledSize", 0)),
                filled_price=float(fill_data.get("price", 0)),
                timestamp=float(fill_data.get("timestamp", 0)),
            )
            
            self.fills[order_id] = fill
            
            logger.info(
                "order_fill_recorded",
                order_id=order_id,
                side=fill.side,
                size=round(fill.filled_size, 2),
                price=round(fill.filled_price, 6),
            )
            
            return fill
        except Exception as e:
            logger.error("fill_recording_failed", error=str(e))
            return None
    
    def has_fill(self, order_id: str) -> bool:
        """Проверяет, заполнен ли ордер"""
        return order_id in self.fills