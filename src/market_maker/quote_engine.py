from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from src.config import Settings
from src.inventory.inventory_manager import InventoryManager

logger = structlog.get_logger(__name__)


@dataclass
class Quote:
    side: str
    price: float
    size: float
    market: str
    token_id: str


class QuoteEngine:
    def __init__(self, settings: Settings, inventory_manager: InventoryManager):
        self.settings = settings
        self.inventory_manager = inventory_manager
        # Минимальный шаг цены на Polymarket обычно 0.001 (1 цент)
        self.tick_size = 0.001 

    def calculate_bid_price(self, mid_price: float, spread_bps: int) -> float:
        """Рассчитываем цену покупки (BID) ниже средней цены"""
        price = mid_price * (1 - spread_bps / 10000)
        # Округляем до ближайшего тика вниз для покупки
        return floor(price / self.tick_size) * self.tick_size

    def calculate_mid_price(self, best_bid: float, best_ask: float) -> float:
        """Рассчитываем середину спреда"""
        if best_bid <= 0 or best_ask <= 0:
            return 0.0
        return (best_bid + best_ask) / 2.0

    def generate_quotes(
        self,
        market_id: str,
        best_bid: float,
        best_ask: float,
        yes_token_id: str,
        no_token_id: str,
    ) -> tuple[Quote | None, Quote | None]:
        """
        Генерируем BUY ордера для YES и NO исходов.
        
        Логика 'Delta Neutral':
        - Покупаем YES дешевле его реальной стоимости.
        - Покупаем NO дешевле его реальной стоимости.
        - Если оба исполняются, мы имеем позицию стоимостью 1.0, купленную за < 1.0.
        """
        # 1. Определяем "справедливую" цену для YES из стакана
        mid_price_yes = self.calculate_mid_price(best_bid, best_ask)
        if mid_price_yes <= 0:
            return (None, None)

        # 2. Справедливая цена NO — это зеркало YES
        mid_price_no = 1.0 - mid_price_yes

        # 3. Рассчитываем наши цены покупки (отступаем спредом внутрь от mid_price)
        # Используем min_spread_bps из конфига
        spread_bps = self.settings.min_spread_bps
        
        yes_bid_price = round(mid_price_yes * (1 - spread_bps / 10000), 3)
        no_bid_price = round(mid_price_no * (1 - spread_bps / 10000), 3)

        # Страховка: цена не может быть ниже 0.001
        yes_bid_price = max(yes_bid_price, 0.001)
        no_bid_price = max(no_bid_price, 0.001)

        # 4. Проверка прибыльности: сумма цен должна быть строго меньше 1.0
        # Если сумма >= 1.0, мы покупаем "воздух" или торгуем в убыток
        total_cost = yes_bid_price + no_bid_price
        if total_cost >= 0.999: # Оставляем запас хотя бы в 1 тик
            logger.warning("negative_edge_detected", 
                           total_cost=total_cost, 
                           yes_p=yes_bid_price, 
                           no_p=no_bid_price)
            # Пытаемся агрессивно снизить цены, чтобы войти в профит
            yes_bid_price -= 0.001
            no_bid_price -= 0.001

        # 5. Определяем размеры позиций
        base_size = self.settings.default_size
        yes_size = self.inventory_manager.get_quote_size_yes(base_size, yes_bid_price)
        no_size = self.inventory_manager.get_quote_size_no(base_size, no_bid_price)

        yes_quote = None
        no_quote = None

        # Формируем котировку на BUY YES
        if self.inventory_manager.can_quote_yes(yes_size):
            yes_quote = Quote(
                side="BUY",
                price=yes_bid_price,
                size=yes_size,
                market=market_id,
                token_id=yes_token_id,
            )

        # Формируем котировку на BUY NO
        if self.inventory_manager.can_quote_no(no_size):
            no_quote = Quote(
                side="BUY",
                price=no_bid_price,
                size=no_size,
                market=market_id,
                token_id=no_token_id,
            )

        # 6. Логирование для мониторинга прибыли (Edge)
        if yes_quote and no_quote:
            edge = 1.0 - (yes_quote.price + no_quote.price)
            logger.info("quotes_generated",
                        edge_per_contract=round(edge, 4),
                        yes_price=yes_quote.price,
                        no_price=no_quote.price,
                        is_balanced=True)

        return (yes_quote, no_quote)

    def _validate_quotes(
        self,
        yes_quote: Quote | None,
        no_quote: Quote | None,
        best_bid: float,
        best_ask: float,
    ) -> bool:
        """Проверка, что наши цены конкурентоспособны, но не слишком агрессивны"""
        if yes_quote:
            # Мы не должны покупать YES дороже, чем его продают прямо сейчас (ask)
            if yes_quote.price >= best_ask:
                return False
        
        if no_quote:
            # Аналогично для NO: цена NO_bid не должна быть выше (1 - YES_bid)
            if no_quote.price >= (1.0 - best_bid):
                return False
                
        return True

    def adjust_for_inventory_skew(self, base_size: float, side: str) -> float:
        """
        Если у нас скопилось слишком много YES, уменьшаем размер покупки YES
        и увеличиваем (или оставляем) размер покупки NO.
        """
        inventory = self.inventory_manager.inventory
        # Если YES в портфеле > 70%, режем объем новых покупок YES
        if inventory.yes_balance > (inventory.total_balance * 0.7):
            return base_size * 0.5
        return base_size