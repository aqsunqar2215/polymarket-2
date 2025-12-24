from __future__ import annotations

import structlog
from src.inventory.inventory_manager import InventoryManager

logger = structlog.get_logger(__name__)


class StopLossManager:
    """
    Управляет stop loss логикой.
    
    Если позиция идет в минус больше чем STOP_LOSS_PCT - закрываем всё и бежим!
    """

    def __init__(
        self,
        inventory_manager: InventoryManager,
        stop_loss_pct: float = 10.0,
    ):
        self.inventory_manager = inventory_manager
        self.stop_loss_pct = stop_loss_pct
        
        # Отслеживаем entry prices для расчета потерь
        self.entry_prices: dict[str, float] = {
            "yes": None,
            "no": None,
        }
        
        self.stop_loss_triggered = False
        logger.info(
            "stop_loss_manager_initialized",
            stop_loss_pct=stop_loss_pct,
        )

    def record_entry(self, token_id: str, price: float):
        """
        Записываем entry price для позиции.
        
        Args:
            token_id: "yes" или "no"
            price: цена вхождения
        """
        if token_id in self.entry_prices:
            self.entry_prices[token_id] = price
            logger.debug(
                "entry_price_recorded",
                token_id=token_id,
                price=round(price, 6),
            )

    def check_stop_loss(
        self,
        yes_position: float,
        no_position: float,
        current_yes_price: float,
    ) -> bool:
        """
        Проверяем нужен ли stop loss.
        
        Рассчитываем P&L позиции и если убыток > STOP_LOSS_PCT - триггерим SL.
        
        Args:
            yes_position: количество YES контрактов (может быть отрицательно если short)
            no_position: количество NO контрактов (может быть отрицательно если short)
            current_yes_price: текущая цена YES на рынке
            
        Returns:
            True если нужно триггерить stop loss
        """
        if self.stop_loss_triggered:
            return False  # Уже триггерили один раз

        if yes_position == 0 and no_position == 0:
            return False  # Нет позиций

        # Рассчитываем текущую стоимость позиции
        yes_value = yes_position * current_yes_price
        no_value = no_position * (1.0 - current_yes_price)
        total_value = yes_value + no_value

        # Если позиция нулевая или очень маленькая - не триггерим
        if abs(total_value) < 0.01:
            return False

        # Рассчитываем начальную стоимость позиции
        if self.entry_prices["yes"] and yes_position != 0:
            yes_entry_value = yes_position * self.entry_prices["yes"]
        else:
            yes_entry_value = 0

        if self.entry_prices["no"] and no_position != 0:
            no_entry_value = no_position * self.entry_prices["no"]
        else:
            no_entry_value = 0

        total_entry_value = yes_entry_value + no_entry_value

        if total_entry_value == 0:
            return False  # Не знаем entry price

        # Рассчитываем процент потерь
        pnl = total_value - total_entry_value
        loss_pct = (pnl / total_entry_value * 100) if total_entry_value != 0 else 0

        # Если потери превышают лимит
        if loss_pct < -self.stop_loss_pct:
            logger.warning(
                "stop_loss_triggered",
                loss_pct=round(loss_pct, 2),
                limit_pct=-self.stop_loss_pct,
                yes_position=round(yes_position, 2),
                no_position=round(no_position, 2),
                current_yes_price=round(current_yes_price, 6),
                pnl=round(pnl, 4),
            )
            self.stop_loss_triggered = True
            return True

        return False

    def should_close_position(self) -> bool:
        """Проверяем нужно ли закрывать позицию."""
        return self.stop_loss_triggered

    def reset(self):
        """Резетим stop loss после закрытия позиции."""
        self.stop_loss_triggered = False
        self.entry_prices = {
            "yes": None,
            "no": None,
        }
        logger.info("stop_loss_manager_reset")