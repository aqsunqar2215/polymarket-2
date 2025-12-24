from __future__ import annotations
from dataclasses import dataclass
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
    dist_bps: int = 0

class QuoteEngine:
    def __init__(self, settings: Settings, inventory_manager: InventoryManager):
        self.settings = settings
        self.inventory_manager = inventory_manager
        self.tick_size = 0.001 

    def calculate_dist_bps(self, my_price: float, market_price: float) -> int:
        if market_price <= 0: return 0
        return int((abs(my_price - market_price) / market_price) * 10000)

    def generate_quotes(
        self,
        market_id: str,
        best_bid: float,
        best_ask: float,
        yes_token_id: str,
        no_token_id: str,
    ) -> tuple[Quote | None, Quote | None]:
        mid_yes = (best_bid + best_ask) / 2.0
        if mid_yes <= 0: return (None, None)
        mid_no = 1.0 - mid_yes

        spread_bps = self.settings.min_spread_bps
        yes_p = round(max(mid_yes * (1 - spread_bps / 10000), self.tick_size), 3)
        no_p = round(max(mid_no * (1 - spread_bps / 10000), self.tick_size), 3)

        yes_p = self.inventory_manager.apply_skew_to_price(yes_p, is_yes=True)
        no_p = self.inventory_manager.apply_skew_to_price(no_p, is_yes=False)

        if (yes_p + no_p) >= 0.999:
            logger.warning("negative_edge_detected", total_cost=round(yes_p + no_p, 3), yes_p=yes_p, no_p=no_p)
            while (yes_p + no_p) >= 0.999:
                yes_p = round(yes_p - self.tick_size, 3)
                no_p = round(no_p - self.tick_size, 3)
                if yes_p <= self.tick_size or no_p <= self.tick_size: break

        edge = round(1.0 - (yes_p + no_p), 4)
        dist_yes = self.calculate_dist_bps(yes_p, best_bid)
        dist_no = self.calculate_dist_bps(no_p, round(1.0 - best_ask, 3))

        yes_size = self.inventory_manager.get_quote_size_yes(self.settings.default_size, yes_p)
        no_size = self.inventory_manager.get_quote_size_no(self.settings.default_size, no_p)

        logger.info("quotes_generated", 
                    edge_per_contract=edge, 
                    yes_price=yes_p, 
                    no_price=no_p, 
                    is_balanced=self.inventory_manager.inventory.is_balanced())

        return (
            Quote("BUY", yes_p, yes_size, market_id, yes_token_id, dist_yes),
            Quote("BUY", no_p, no_size, market_id, no_token_id, dist_no)
        )