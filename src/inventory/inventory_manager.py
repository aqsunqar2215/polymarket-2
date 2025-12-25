from __future__ import annotations
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class Inventory:
    yes_position: float = 0.0
    no_position: float = 0.0
    net_exposure_usd: float = 0.0
    total_value_usd: float = 0.0

    def update(self, yes_delta: float, no_delta: float, price: float):
        self.yes_position += yes_delta
        self.no_position += no_delta
        yes_val = self.yes_position * price
        no_val = self.no_position * (1.0 - price)
        self.net_exposure_usd = yes_val - no_val
        self.total_value_usd = yes_val + no_val

    def is_balanced(self, threshold_usd: float = 10.0) -> bool:
        """Проверяет, находится ли риск в пределах допустимого порога."""
        return abs(self.net_exposure_usd) < threshold_usd

class InventoryManager:
    def __init__(self, max_exposure_usd: float, min_exposure_usd: float, target_balance: float = 0.0):
        self.max_exposure_usd = max_exposure_usd
        self.min_exposure_usd = min_exposure_usd
        self.target_balance = target_balance
        self.inventory = Inventory()

    def apply_skew_to_price(self, price: float, is_yes: bool) -> float:
        """Смещает цену в зависимости от накопленного инвентаря."""
        exposure = self.inventory.net_exposure_usd
        # 0.005 означает смещение на 0.5 цента при существенном перекосе
        sensitivity = 0.005
        skew_factor = exposure / max(self.max_exposure_usd, 1.0)
        adjustment = round(skew_factor * sensitivity, 3)

        if is_yes:
            new_price = price - adjustment
        else:
            new_price = price + adjustment

        return round(max(0.001, min(0.999, new_price)), 3)

    def get_quote_size_yes(self, base_size: float, price: float) -> float:
        if (self.inventory.net_exposure_usd + (base_size * price)) > self.max_exposure_usd:
            return 0.0
        return base_size

    def get_quote_size_no(self, base_size: float, price: float) -> float:
        if (self.inventory.net_exposure_usd - (base_size * (1-price))) < self.min_exposure_usd:
            return 0.0
        return base_size