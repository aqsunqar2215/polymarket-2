"""
Advanced Dynamic Pricing Engine for Polymarket Market Maker Bot
Реализует все требования из плана: Market Mirroring, Volatility Protection, L2 Imbalance
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PricingContext:
    """Контекст для расчета цен"""
    market_id: str
    mid_price: float
    volatility: float  # Волатильность (0-1, где 1 = очень волатильно)
    imbalance: float  # Дисбаланс стакана (-1 до +1)
    best_bid: float
    best_ask: float
    spread_bps: int  # Текущий спред в basis points
    inventory_skew: float  # Перекос инвентаря (-1 до +1)


class DynamicSpreadEngine:
    """
    Модуль 1: Dynamic Spread Engine

    Реализует:
    - Market Mirroring: выстраивается на 1 тик лучше конкурентов
    - Volatility Protection: расширяет спред при высокой волатильности
    - L2 Imbalance: корректирует спред по дисбалансу стакана
    """

    def __init__(
            self,
            base_spread_bps: int = 10,  # 0.1% базовый спред
            min_spread_bps: int = 5,    # 0.05% минимум
            max_spread_bps: int = 500,  # 5% максимум при панике
    ):
        self.base_spread_bps = base_spread_bps
        self.min_spread_bps = min_spread_bps
        self.max_spread_bps = max_spread_bps
        self.tick_size = 0.001  # 0.1 цента
        self.rebate_bps = 10    # На 0.1% лучше конкурентов для получения rebate

    def calculate_dynamic_spread(
            self,
            context: PricingContext,
    ) -> int:
        """
        Рассчитать динамический спред в зависимости от условий рынка.

        Логика:
        1. Base spread = параметр конфига
        2. Volatility adjustment: если волатильность высокая -> расширяем
        3. Imbalance adjustment: если стакан дисбалансирован -> расширяем
        4. Inventory skew adjustment: если инвентарь перекошен -> расширяем

        Returns:
            spread_bps: спред в basis points
        """
        spread = self.base_spread_bps

        # 1. Volatility Protection (0-4x multiplier)
        # При волатильности 0.5 спред становится 1.5x, при 1.0 -> 5x
        if context.volatility > 0.3:
            volatility_multiplier = 1.0 + (context.volatility ** 2) * 4.0
            spread = int(spread * volatility_multiplier)
            logger.debug(
                "volatility_protection_applied",
                volatility=round(context.volatility, 4),
                multiplier=round(volatility_multiplier, 2),
                spread_bps=spread,
            )

        # 2. L2 Imbalance Protection
        # Если спред очень узкий (< 10 bps) и стакан дисбалансирован -> расширяем
        imbalance_adjustment = 0
        if abs(context.imbalance) > 0.3:
            imbalance_adjustment = int(abs(context.imbalance) * 100)
            spread = max(spread, imbalance_adjustment)
            logger.debug(
                "imbalance_protection_applied",
                imbalance=round(context.imbalance, 4),
                adjustment_bps=imbalance_adjustment,
            )

        # 3. Inventory Skew Protection
        # Если инвентарь перекошен > 60% -> расширяем спред
        if abs(context.inventory_skew) > 0.6:
            skew_multiplier = 1.0 + abs(context.inventory_skew) * 0.5
            spread = int(spread * skew_multiplier)
            logger.debug(
                "inventory_skew_protection_applied",
                skew=round(context.inventory_skew, 4),
                spread_bps=spread,
            )

        # Убедимся, что спред в допустимых пределах
        spread = max(self.min_spread_bps, min(spread, self.max_spread_bps))

        return spread

    def mirror_market(
            self,
            context: PricingContext,
    ) -> tuple[float, float]:
        """
        Market Mirroring: выставляемся на 1 тик лучше конкурентов.

        Логика:
        1. Рассчитываем динамический спред
        2. Выставляемся на 1 тик (0.001) лучше конкурентов
        3. Добавляем random offset чтобы нас не "пинговали"

        Returns:
            (bid_price, ask_price)
        """
        # Динамический спред
        spread_bps = self.calculate_dynamic_spread(context)
        spread_decimal = spread_bps / 10000.0

        # Расчет наших цен
        bid_price = context.mid_price - (spread_decimal / 2.0)
        ask_price = context.mid_price + (spread_decimal / 2.0)

        # Mirroring: выставляемся на 1 тик лучше
        # Если конкуренты стоят на mid_price ± spread, мы стоим на mid ± spread - tick
        bid_price = max(bid_price - self.tick_size, 0.001)
        ask_price = min(ask_price + self.tick_size, 0.999)

        # Добавляем случайное смещение (±0.5 тика) чтобы избежать pinning
        random_offset = random.randint(-50, 50) * 0.00001
        bid_price = round(bid_price + random_offset, 3)
        ask_price = round(ask_price + random_offset, 3)

        logger.info(
            "market_mirrored",
            market_id=context.market_id,
            bid=round(bid_price, 6),
            ask=round(ask_price, 6),
            spread_bps=spread_bps,
            volatility=round(context.volatility, 4),
            imbalance=round(context.imbalance, 4),
        )

        return (bid_price, ask_price)


class InventorySkewManager:
    """
    Модуль 2: Улучшенный Inventory Management (Inventory Skew 2.0)

    Реализует:
    - Aggressive Skew: если позиция > 60%, снижаем цену на одну сторону
    - Position Sizing: динамический размер ордера в зависимости от баланса
    - Auto-Hedge: автоматическое закрытие при критическом дисбалансе
    """

    def __init__(
            self,
            base_size_usd: float = 100.0,
            max_exposure_usd: float = 10000.0,
    ):
        self.base_size_usd = base_size_usd
        self.max_exposure_usd = max_exposure_usd

    def calculate_position_sizing(
            self,
            current_balance_usd: float,
            inventory_skew: float,  # -1 (all NO) to +1 (all YES)
            mid_price: float,
    ) -> tuple[float, float]:
        """
        Position Sizing: Рассчитываем размер ордера в зависимости от баланса.

        Логика:
        1. При идеальном балансе (skew=0) -> base_size
        2. При перекосе > 60% -> размер падает (пытаемся перебалансироваться)
        3. При критическом перекосе (>80%) -> пытаемся активно закрыться

        Returns:
            (yes_order_size_usd, no_order_size_usd)
        """
        # Базовый размер для идеально сбалансированного портфеля
        yes_size = self.base_size_usd
        no_size = self.base_size_usd

        # Агрессивная коррекция при перекосе
        if abs(inventory_skew) > 0.6:
            # Понижаем размер на переизбыточной стороне
            reduction = abs(inventory_skew) - 0.5  # 10-50% reduction

            if inventory_skew > 0.6:  # Много YES
                yes_size = max(10, yes_size * (1.0 - reduction))
                no_size = self.base_size_usd * 1.5  # Увеличиваем NO
            else:  # Много NO
                no_size = max(10, no_size * (1.0 - reduction))
                yes_size = self.base_size_usd * 1.5  # Увеличиваем YES

        # Проверка exposure limits
        available_usd = self.max_exposure_usd - current_balance_usd
        if available_usd < yes_size:
            yes_size = max(10, available_usd * 0.8)

        available_usd = self.max_exposure_usd + current_balance_usd
        if available_usd < no_size:
            no_size = max(10, available_usd * 0.8)

        return (round(yes_size, 2), round(no_size, 2))

    def apply_inventory_skew_to_prices(
            self,
            bid_price: float,
            ask_price: float,
            inventory_skew: float,
            skew_intensity: float = 0.005,  # На сколько пунктов смещать при 100% перекосе
    ) -> tuple[float, float]:
        """
        Aggressive Skew: смещаем цены в зависимости от перекоса инвентаря.

        Логика:
        1. Если skew = 0.8 (80% YES) -> снижаем цену на YES, повышаем на NO
        2. Это делает NO более привлекательным для покупки (т.е. продаже YES)
        3. Интенсивность смещения пропорциональна перекосу

        Returns:
            (adjusted_bid, adjusted_ask) где bid относится к YES, ask к NO
        """
        adjustment = inventory_skew * skew_intensity

        # Если много YES -> понижаем bid на YES
        if inventory_skew > 0:
            bid_price = max(0.001, bid_price - adjustment)
            ask_price = min(0.999, ask_price + adjustment)
        # Если много NO -> понижаем ask на NO (т.е. повышаем цену)
        else:
            bid_price = min(0.999, bid_price - adjustment)
            ask_price = max(0.001, ask_price + adjustment)

        return (round(bid_price, 3), round(ask_price, 3))

    async def check_critical_skew(
            self,
            inventory_skew: float,
            yes_position: float,
            no_position: float,
            current_price: float,
    ) -> dict[str, Any]:
        """
        Auto-Hedge: проверяем критический дисбаланс.

        Returns:
            {
                "should_hedge": bool,
                "side_to_close": "YES" | "NO",
                "size": float,
                "reason": str,
            }
        """
        critical_threshold = 0.8

        if abs(inventory_skew) > critical_threshold:
            side_to_close = "YES" if inventory_skew > 0 else "NO"
            position_to_close = yes_position if side_to_close == "YES" else no_position

            # Закрываем 50% позиции
            hedge_size = position_to_close * 0.5 * current_price

            logger.warning(
                "critical_skew_detected",
                skew=round(inventory_skew, 4),
                side_to_close=side_to_close,
                hedge_size=round(hedge_size, 2),
            )

            return {
                "should_hedge": True,
                "side_to_close": side_to_close,
                "size": hedge_size,
                "reason": f"Critical skew: {abs(inventory_skew):.1%}",
            }

        return {
            "should_hedge": False,
            "side_to_close": None,
            "size": 0.0,
            "reason": "Skew within acceptable range",
        }


class OrderManagementSystem:
    """
    Модуль 3: Order Management System (OMS)

    Реализует:
    - Smart Cancel/Replace: обновляем ордера каждые 2-5 сек если цена изменилась > 0.1%
    - Partial Fill Handling: пересчитываем размер при частичном исполнении
    - Anti-Crossing: убеждаемся, что наши ордера не cross друг с другом
    """

    def __init__(self, order_lifetime_ms: int = 3000):
        self.order_lifetime_ms = order_lifetime_ms
        self.active_orders: dict[str, dict[str, Any]] = {}
        self.price_tolerance_bps = 10  # Обновляем если цена сместилась на 10 bps
        self.last_update_time = 0.0

    def should_update_orders(
            self,
            current_mid_price: float,
            last_mid_price: float,
    ) -> bool:
        """
        Smart Cancel/Replace: решить нужно ли обновлять ордера.

        Условия для обновления:
        1. Цена сместилась больше чем на tolerance (10 bps)
        2. Прошло более чем 2 секунды с последнего обновления
        3. Есть активные ордера

        Returns:
            True если нужно обновить
        """
        if not self.active_orders:
            return False

        time_since_update = time.time() - self.last_update_time
        price_change_bps = (
                abs(current_mid_price - last_mid_price) / last_mid_price * 10000
        )

        should_update = (
                price_change_bps > self.price_tolerance_bps
                or time_since_update > 2.0
        )

        if should_update:
            logger.debug(
                "orders_should_update",
                price_change_bps=round(price_change_bps, 2),
                time_since_update=round(time_since_update, 2),
            )

        return should_update

    def handle_partial_fill(
            self,
            order_id: str,
            filled_size: float,
            total_size: float,
    ) -> dict[str, Any]:
        """
        Partial Fill Handling: пересчитываем оставшуюся часть ордера.

        Returns:
            {
                "should_cancel": bool,
                "remaining_size": float,
                "new_price": float,
            }
        """
        if order_id not in self.active_orders:
            return {"should_cancel": True}

        order = self.active_orders[order_id]
        remaining_size = total_size - filled_size

        # Если исполнено < 20% - оставляем ордер
        # Если исполнено 20-80% - пересчитываем размер
        # Если исполнено > 80% - отменяем

        fill_ratio = filled_size / total_size

        if fill_ratio < 0.2:
            return {"should_cancel": False, "remaining_size": total_size}
        elif 0.2 <= fill_ratio <= 0.8:
            logger.info(
                "partial_fill_detected",
                order_id=order_id,
                filled_ratio=round(fill_ratio, 2),
                remaining_size=round(remaining_size, 2),
            )
            return {
                "should_cancel": False,
                "remaining_size": max(10, remaining_size),
            }
        else:
            logger.info("order_mostly_filled", order_id=order_id)
            return {"should_cancel": True, "remaining_size": 0}

    def check_anti_crossing(
            self,
            bid_price: float,
            ask_price: float,
    ) -> tuple[bool, str]:
        """
        Anti-Crossing Logic: убеждаемся, что bid < ask.

        Returns:
            (is_valid, reason)
        """
        if bid_price >= ask_price:
            return (
                False,
                f"Invalid spread: bid {bid_price} >= ask {ask_price}",
            )

        spread_decimal = ask_price - bid_price
        spread_bps = (spread_decimal / ((bid_price + ask_price) / 2)) * 10000

        if spread_bps < 1:  # < 1 bps is unrealistic
            return (False, f"Spread too tight: {spread_bps:.2f} bps")

        return (True, "Valid spread")


class MetricsCalculator:
    """
    Модуль 4: Metrics & Health Check (Logging & Monitoring)

    Реализует:
    - PnL Tracker: отслеживаем прибыль
    - Fill Rate: статистика по исполнению ордеров
    - Health Checks: проверяем статус системы
    """

    def __init__(self):
        self.total_orders_placed = 0
        self.total_orders_filled = 0
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.start_time = time.time()

    def calculate_fill_rate(self) -> float:
        """Рассчитать процент исполненных ордеров"""
        if self.total_orders_placed == 0:
            return 0.0
        return (self.total_orders_filled / self.total_orders_placed) * 100

    def record_order_placed(self):
        self.total_orders_placed += 1

    def record_order_filled(self, pnl: float = 0.0):
        self.total_orders_filled += 1
        self.realized_pnl += pnl

    def get_health_report(self) -> dict[str, Any]:
        """Полный отчет о здоровье системы"""
        fill_rate = self.calculate_fill_rate()

        # Диагностика
        health_status = "GOOD"
        if fill_rate < 10:
            health_status = "WARNING"  # Спред слишком широкий
        elif fill_rate > 90:
            health_status = "CAUTION"  # Спред слишком узкий

        return {
            "fill_rate_percent": round(fill_rate, 2),
            "total_orders_placed": self.total_orders_placed,
            "total_orders_filled": self.total_orders_filled,
            "realized_pnl": round(self.realized_pnl, 4),
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "total_pnl": round(self.realized_pnl + self.unrealized_pnl, 4),
            "uptime_minutes": round((time.time() - self.start_time) / 60, 2),
            "health_status": health_status,
        }

    def log_metrics(self):
        """Логировать метрики"""
        report = self.get_health_report()

        status_emoji = "✅" if report["health_status"] == "GOOD" else "⚠️"

        logger.info(
            "metrics_report",
            status=status_emoji + " " + report["health_status"],
            fill_rate=f"{report['fill_rate_percent']:.1f}%",
            pnl=f"${report['total_pnl']:.4f}",
            orders_placed=report["total_orders_placed"],
            orders_filled=report["total_orders_filled"],
            uptime_minutes=report["uptime_minutes"],
        )