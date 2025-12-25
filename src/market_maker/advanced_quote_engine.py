"""
Advanced Quote Engine - интегрирует все модули динамического ценообразования
Это замена/расширение существующего src/market_maker/quote_engine.py
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog

from src.config import Settings
from src.inventory.inventory_manager import InventoryManager

# Импортируем новые модули
from dynamic_pricing_system import (
    DynamicSpreadEngine,
    InventorySkewManager,
    OrderManagementSystem,
    MetricsCalculator,
    PricingContext,
)

logger = structlog.get_logger(__name__)


@dataclass
class AdvancedQuote:
    """Продвинутая котировка с метаданными"""
    side: str  # "BUY"
    price: float
    size: float
    market: str
    token_id: str

    # Метаданные
    edge_per_contract: float  # Наша прибыль за контракт
    spread_bps: int
    volatility: float
    imbalance: float
    inventory_skew: float
    confidence: float  # Уверенность в цене (0-1)

    def __repr__(self):
        return (
            f"Quote({self.side} @ {self.price:.3f}, size=${self.size:.2f}, "
            f"edge={self.edge_per_contract:.4f}, spread={self.spread_bps}bps)"
        )


class AdvancedQuoteEngine:
    """
    Продвинутый Quote Engine с полной интеграцией:
    1. Dynamic Spread Engine
    2. Inventory Skew Manager
    3. Order Management System
    4. Metrics Calculator
    """

    def __init__(self, settings: Settings, inventory_manager: InventoryManager):
        self.settings = settings
        self.inventory_manager = inventory_manager

        # Инициализируем компоненты
        self.spread_engine = DynamicSpreadEngine(
            base_spread_bps=settings.min_spread_bps,
            min_spread_bps=max(5, settings.min_spread_bps),
            max_spread_bps=500,
        )

        self.skew_manager = InventorySkewManager(
            base_size_usd=settings.default_size,
            max_exposure_usd=settings.max_exposure_usd,
        )

        self.oms = OrderManagementSystem(
            order_lifetime_ms=settings.order_lifetime_ms,
        )

        self.metrics = MetricsCalculator()

        # State tracking
        self.last_mid_price = 0.5
        self.last_volatility = 0.0
        self.price_history: list[tuple[float, float]] = []  # (price, timestamp)
        self.max_history_size = 100

    def _calculate_volatility(self, prices: list[float]) -> float:
        """
        Рассчитать волатильность из истории цен.

        Использует стандартное отклонение за последние N периодов.
        Returns: волатильность в диапазоне [0, 1]
        """
        if len(prices) < 2:
            return 0.0

        # Calculate returns
        returns = []
        for i in range(1, len(prices)):
            ret = (prices[i] - prices[i - 1]) / prices[i - 1]
            returns.append(ret)

        # Standard deviation of returns
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std_dev = variance ** 0.5

        # Normalize to [0, 1]
        volatility = min(std_dev * 100, 1.0)

        return max(0.0, volatility)

    def _calculate_imbalance(
            self,
            bids: list[tuple[float, float]],
            asks: list[tuple[float, float]],
    ) -> float:
        """
        Рассчитать дисбаланс стакана из L2 orderbook.

        Returns:
            float: от -1 (все биды) до +1 (все аски)
        """
        if not bids or not asks:
            return 0.0

        bid_volume = sum(size for _, size in bids[:5])
        ask_volume = sum(size for _, size in asks[:5])

        if bid_volume + ask_volume == 0:
            return 0.0

        imbalance = (ask_volume - bid_volume) / (ask_volume + bid_volume)
        return max(-1.0, min(1.0, imbalance))

    def _calculate_inventory_skew(self) -> float:
        """
        Рассчитать перекос инвентаря.

        Returns:
            float: от -1 (all NO) до +1 (all YES)
        """
        inv = self.inventory_manager.inventory
        total = inv.yes_position + inv.no_position

        if total == 0:
            return 0.0

        skew = (inv.yes_position - inv.no_position) / total
        return max(-1.0, min(1.0, skew))

    def generate_advanced_quotes(
            self,
            market_id: str,
            mid_price: float,
            best_bid: float,
            best_ask: float,
            yes_token_id: str,
            no_token_id: str,
            orderbook_data: dict[str, Any] | None = None,
    ) -> tuple[AdvancedQuote | None, AdvancedQuote | None]:
        """
        Генерировать продвинутые котировки с полным использованием всех модулей.

        Процесс:
        1. Собрать контекст (volatility, imbalance, skew)
        2. Рассчитать динамический спред
        3. Применить inventory skew к ценам
        4. Проверить anti-crossing
        5. Рассчитать размеры ордеров
        6. Вернуть котировки с метаданными
        """
        start_time = time.time()

        try:
            # === ШАГ 1: Сбор контекста ===

            # История цен для волатильности
            self.price_history.append((mid_price, time.time()))
            if len(self.price_history) > self.max_history_size:
                self.price_history.pop(0)

            prices = [p for p, _ in self.price_history]
            volatility = self._calculate_volatility(prices)

            # Дисбаланс стакана из L2 orderbook
            imbalance = 0.0
            if orderbook_data and orderbook_data.get("l2_available"):
                l2_data = orderbook_data.get("l2_data", {})
                if l2_data.get("yes"):
                    yes_l2 = l2_data["yes"]
                    imbalance = self._calculate_imbalance(
                        yes_l2.get("bids", []),
                        yes_l2.get("asks", []),
                    )

            # Перекос инвентаря
            inventory_skew = self._calculate_inventory_skew()

            # Текущий спред на рынке
            current_spread_bps = (
                int((best_ask - best_bid) / mid_price * 10000)
                if best_ask > best_bid > 0
                else 100
            )

            # === ШАГ 2: Создать контекст для расчетов ===

            pricing_context = PricingContext(
                market_id=market_id,
                mid_price=mid_price,
                volatility=volatility,
                imbalance=imbalance,
                best_bid=best_bid,
                best_ask=best_ask,
                spread_bps=current_spread_bps,
                inventory_skew=inventory_skew,
            )

            # === ШАГ 3: Dynamic Spread Engine ===

            bid_price, ask_price = self.spread_engine.mirror_market(pricing_context)

            logger.debug(
                "dynamic_spread_calculated",
                mid=round(mid_price, 6),
                bid=round(bid_price, 6),
                ask=round(ask_price, 6),
                volatility=round(volatility, 4),
                imbalance=round(imbalance, 4),
            )

            # === ШАГ 4: Inventory Skew Application ===

            # Применяем перекос инвентаря к ценам
            bid_price, ask_price = self.skew_manager.apply_inventory_skew_to_prices(
                bid_price,
                ask_price,
                inventory_skew,
                skew_intensity=0.005,
            )

            # === ШАГ 5: Anti-Crossing Check ===

            is_valid, reason = self.oms.check_anti_crossing(bid_price, ask_price)
            if not is_valid:
                logger.warning("anti_crossing_validation_failed", reason=reason)
                return (None, None)

            # === ШАГ 6: Position Sizing ===

            current_balance = self.inventory_manager.inventory.net_exposure_usd
            yes_size, no_size = self.skew_manager.calculate_position_sizing(
                current_balance,
                inventory_skew,
                mid_price,
            )

            # === ШАГ 7: Confidence Score ===

            # Уверенность в цене зависит от волатильности и дисбаланса
            confidence = 1.0
            if volatility > 0.5:
                confidence -= 0.2
            if abs(imbalance) > 0.5:
                confidence -= 0.1
            if abs(inventory_skew) > 0.7:
                confidence -= 0.1

            confidence = max(0.5, min(1.0, confidence))

            # === ШАГ 8: Edge Calculation ===

            edge = 1.0 - (bid_price + ask_price)

            # === ШАГ 9: Логирование ===

            elapsed_ms = (time.time() - start_time) * 1000
            dynamic_spread = int((ask_price - bid_price) / mid_price * 10000)

            logger.info(
                "advanced_quotes_generated",
                market_id=market_id,
                bid=round(bid_price, 6),
                ask=round(ask_price, 6),
                yes_size=round(yes_size, 2),
                no_size=round(no_size, 2),
                edge_per_contract=round(edge, 4),
                dynamic_spread_bps=dynamic_spread,
                volatility=round(volatility, 4),
                imbalance=round(imbalance, 4),
                inventory_skew=round(inventory_skew, 4),
                confidence=round(confidence, 2),
                gen_latency_ms=round(elapsed_ms, 1),
            )

            # === ШАГ 10: Создать котировки ===

            yes_quote = AdvancedQuote(
                side="BUY",
                price=bid_price,
                size=yes_size,
                market=market_id,
                token_id=yes_token_id,
                edge_per_contract=edge,
                spread_bps=dynamic_spread,
                volatility=volatility,
                imbalance=imbalance,
                inventory_skew=inventory_skew,
                confidence=confidence,
            )

            no_quote = AdvancedQuote(
                side="BUY",
                price=ask_price,
                size=no_size,
                market=market_id,
                token_id=no_token_id,
                edge_per_contract=edge,
                spread_bps=dynamic_spread,
                volatility=volatility,
                imbalance=imbalance,
                inventory_skew=inventory_skew,
                confidence=confidence,
            )

            # === ШАГ 11: Order Lifecycle ===

            # Проверяем нужно ли обновлять ордера
            should_update = self.oms.should_update_orders(mid_price, self.last_mid_price)
            if should_update:
                logger.debug("should_update_orders", mid_change_bps=abs((mid_price - self.last_mid_price) / self.last_mid_price * 10000))

            self.last_mid_price = mid_price
            self.last_volatility = volatility

            # === ШАГ 12: Запись метрик ===

            self.metrics.record_order_placed()
            if self.metrics.total_orders_placed % 50 == 0:
                self.metrics.log_metrics()

            return (yes_quote, no_quote)

        except Exception as e:
            logger.error(
                "advanced_quote_generation_failed",
                error=str(e),
                exc_info=True,
            )
            return (None, None)

    def get_system_health(self) -> dict[str, Any]:
        """Получить полный отчет о здоровье системы"""
        return self.metrics.get_health_report()