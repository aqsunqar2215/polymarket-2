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
    dist_bps: int = 0


class QuoteEngine:
    def __init__(self, settings: Settings, inventory_manager: InventoryManager):
        self.settings = settings
        self.inventory_manager = inventory_manager
        self.tick_size = 0.001
        self.l2_depth_levels = 5  # Analyze top 5 levels for imbalance

    def calculate_imbalance(
        self,
        bids: list[tuple[float, float]] | None,
        asks: list[tuple[float, float]] | None,
    ) -> float:
        """
        Calculate order book imbalance ratio based on top N levels.

        Returns:
            imbalance ratio in range [-1, 1]
            Negative = more volume on bid side (buyers dominate)
            Positive = more volume on ask side (sellers dominate)
            0 = balanced
        """
        if not bids or not asks:
            return 0.0

        try:
            # Sum volumes for top levels
            bid_volume = sum(
                size for price, size in bids[: self.l2_depth_levels]
            )
            ask_volume = sum(
                size for price, size in asks[: self.l2_depth_levels]
            )

            if bid_volume + ask_volume == 0:
                return 0.0

            # Calculate imbalance: +1 = all ask, -1 = all bid, 0 = balanced
            imbalance = (ask_volume - bid_volume) / (ask_volume + bid_volume)

            return max(-1.0, min(1.0, imbalance))

        except Exception as e:
            logger.debug("imbalance_calculation_failed", error=str(e))
            return 0.0

    def calculate_dist_bps(self, my_price: float, market_price: float) -> int:
        """Calculate distance from market price in basis points"""
        if market_price <= 0:
            return 0
        return int((abs(my_price - market_price) / market_price) * 10000)

    def _calculate_l2_mid_price(
        self,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        depth_levels: int = 3,
    ) -> float:
        """
        Calculate volume-weighted mid price from L2 orderbook.

        Uses top N levels for more accurate mid-price calculation.
        """
        try:
            # Get weighted bid price
            bid_weights = []
            for price, size in bids[:depth_levels]:
                bid_weights.append(price * size)

            # Get weighted ask price
            ask_weights = []
            for price, size in asks[:depth_levels]:
                ask_weights.append(price * size)

            bid_volume = sum(size for _, size in bids[:depth_levels])
            ask_volume = sum(size for _, size in asks[:depth_levels])

            if bid_volume == 0 or ask_volume == 0:
                # Fallback to simple mid
                return (bids[0][0] + asks[0][0]) / 2.0

            weighted_bid = sum(bid_weights) / bid_volume
            weighted_ask = sum(ask_weights) / ask_volume

            mid = (weighted_bid + weighted_ask) / 2.0

            return max(0.001, min(0.999, mid))

        except Exception as e:
            logger.debug("l2_mid_price_calculation_failed", error=str(e))
            # Fallback to simple mid
            if bids and asks:
                return (bids[0][0] + asks[0][0]) / 2.0
            return 0.5

    def generate_quotes(
        self,
        market_id: str,
        best_bid: float,
        best_ask: float,
        yes_token_id: str,
        no_token_id: str,
        orderbook_data: dict[str, Any] | None = None,
    ) -> tuple[Quote | None, Quote | None]:
        """
        Generate quotes using L2 orderbook if available, with fallback to Gamma API.

        Args:
            market_id: Market ID
            best_bid: Best bid from Gamma/L2
            best_ask: Best ask from Gamma/L2
            yes_token_id: YES token ID
            no_token_id: NO token ID
            orderbook_data: dict from get_orderbook() with L2 data if available

        Returns:
            Tuple of (yes_quote, no_quote) or (None, None) if generation fails
        """
        try:
            # Extract L2 data if available
            yes_l2 = None
            no_l2 = None
            imbalance = 0.0
            using_l2 = False

            if orderbook_data and orderbook_data.get("l2_available"):
                l2_data = orderbook_data.get("l2_data")
                if l2_data:
                    yes_l2 = l2_data.get("yes")
                    no_l2 = l2_data.get("no")
                    using_l2 = True

                    if yes_l2 and "bids" in yes_l2 and "asks" in yes_l2:
                        imbalance = self.calculate_imbalance(
                            yes_l2["bids"],
                            yes_l2["asks"],
                        )

            # Calculate mid price
            if using_l2 and yes_l2 and "bids" in yes_l2 and "asks" in yes_l2:
                mid_yes = self._calculate_l2_mid_price(
                    yes_l2["bids"],
                    yes_l2["asks"],
                )
                logger.debug(
                    "using_l2_mid_price",
                    market_id=market_id,
                    mid_yes=round(mid_yes, 6),
                    imbalance=round(imbalance, 4),
                )
            else:
                # Fallback: calculate from best bid/ask
                if best_bid > 0 and best_ask > 0:
                    mid_yes = (best_bid + best_ask) / 2.0
                else:
                    mid_yes = 0.5

            if mid_yes <= 0 or mid_yes >= 1:
                return (None, None)

            mid_no = 1.0 - mid_yes

            # Calculate spread with inventory skew
            spread_bps = self.settings.min_spread_bps

            # Apply inventory skew
            yes_p = round(max(mid_yes * (1 - spread_bps / 10000), self.tick_size), 3)
            no_p = round(max(mid_no * (1 - spread_bps / 10000), self.tick_size), 3)

            yes_p = self.inventory_manager.apply_skew_to_price(yes_p, is_yes=True)
            no_p = self.inventory_manager.apply_skew_to_price(no_p, is_yes=False)

            # Apply imbalance adjustment (push prices away from dominant side)
            if using_l2 and abs(imbalance) > 0.3:
                imbalance_adjustment = imbalance * 0.002  # Max 0.2 cents adjustment
                yes_p = round(yes_p - imbalance_adjustment, 3)
                no_p = round(no_p + imbalance_adjustment, 3)

                logger.debug(
                    "imbalance_adjustment_applied",
                    imbalance=round(imbalance, 4),
                    adjustment=round(imbalance_adjustment, 6),
                )

            # Critical edge protection: ensure positive spread
            while (yes_p + no_p) >= 0.999 and (yes_p > self.tick_size or no_p > self.tick_size):
                yes_p = round(yes_p - self.tick_size, 3)
                no_p = round(no_p - self.tick_size, 3)

            if (yes_p + no_p) >= 0.999:
                logger.warning(
                    "negative_edge_detected",
                    total_cost=round(yes_p + no_p, 3),
                    yes_p=yes_p,
                    no_p=no_p,
                    mid_yes=round(mid_yes, 6),
                    imbalance=round(imbalance, 4),
                )
                return (None, None)

            # Calculate edge (our profit per contract)
            edge = round(1.0 - (yes_p + no_p), 4)

            # Calculate distance from best bid/ask
            dist_yes = self.calculate_dist_bps(yes_p, best_bid)
            dist_no = self.calculate_dist_bps(no_p, round(1.0 - best_ask, 3))

            # Get quote sizes based on inventory
            yes_size = self.inventory_manager.get_quote_size_yes(
                self.settings.default_size,
                yes_p,
            )
            no_size = self.inventory_manager.get_quote_size_no(
                self.settings.default_size,
                no_p,
            )

            logger.info(
                "quotes_generated",
                market_id=market_id,
                edge_per_contract=edge,
                yes_price=yes_p,
                no_price=no_p,
                yes_size=yes_size,
                no_size=no_size,
                is_balanced=self.inventory_manager.inventory.is_balanced(),
                using_l2=using_l2,
                imbalance=round(imbalance, 4),
            )

            return (
                Quote("BUY", yes_p, yes_size, market_id, yes_token_id, dist_yes),
                Quote("BUY", no_p, no_size, market_id, no_token_id, dist_no),
            )

        except Exception as e:
            logger.error("quote_generation_failed", error=str(e), exc_info=True)
            return (None, None)