from __future__ import annotations
import asyncio
import signal
import structlog
import sys
import json
from typing import Any
from dotenv import load_dotenv

from src.config import Settings, get_settings
from src.inventory.inventory_manager import InventoryManager
from src.logging_config import configure_logging
from src.market_maker.quote_engine import QuoteEngine
from src.market_discovery import MarketDiscovery
from src.polymarket.rest_client import PolymarketRestClient

logger = structlog.get_logger(__name__)

class MarketMakerBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.running = False
        self._stop_event = asyncio.Event()
        self.rest_client = PolymarketRestClient(settings)
        self.market_discovery = MarketDiscovery(settings.polymarket_api_url)
        self.inventory_manager = InventoryManager(
            settings.max_exposure_usd, 
            settings.min_exposure_usd, 
            settings.target_inventory_balance
        )
        self.quote_engine = QuoteEngine(settings, self.inventory_manager)
        self.market_id: str | None = None
        self.tokens: list[str] = []

    async def initialize_market(self) -> bool:
        m_id = self.settings.get_market_id()
        if not m_id:
            m_id = await self.market_discovery.interactive_market_selection(
                self.settings.min_volume_24h, 
                self.settings.max_spread_bps
            )
        if m_id:
            self.market_id = m_id
            info = await self.rest_client.get_market_info(m_id)
            raw_tokens = info.get("clobTokenIds", [])
            if isinstance(raw_tokens, str):
                self.tokens = json.loads(raw_tokens)
            else:
                self.tokens = raw_tokens
            logger.info("market_initialized", id=self.market_id, question=info.get("question"))
            return True
        return False

    async def update_loop(self):
        if len(self.tokens) < 2:
            logger.error("missing_token_ids")
            return
        yes_token, no_token = self.tokens[0], self.tokens[1]
        logger.info("starting_quote_loop", refresh_ms=self.settings.quote_refresh_rate_ms)

        while not self._stop_event.is_set():
            try:
                ob = await self.rest_client.get_orderbook(self.market_id)
                bid, ask = ob.get("best_bid", 0), ob.get("best_ask", 0)
                spread = int((ask-bid)/((bid+ask)/2)*10000) if (bid+ask)>0 else 0
                logger.info("market_status", bid=bid, ask=ask, spread_bps=spread)

                yes_q, no_q = self.quote_engine.generate_quotes(self.market_id, bid, ask, yes_token, no_token)

                if yes_q:
                    logger.info("quote_yes", side=yes_q.side, price=yes_q.price, size=yes_q.size, dist_bps=yes_q.dist_bps)
                if no_q:
                    logger.info("quote_no", side=no_q.side, price=no_q.price, size=no_q.size, dist_bps=no_q.dist_bps)

                await asyncio.sleep(self.settings.quote_refresh_rate_ms / 1000.0)
            except Exception as e:
                logger.error("loop_error", error=str(e))
                await asyncio.sleep(2)

    async def run(self):
        self.running = True
        if await self.initialize_market():
            await self.update_loop()

    async def stop(self):
        if not self.running: return
        self._stop_event.set()
        self.running = False
        await self.rest_client.close()
        await self.market_discovery.close()

async def bootstrap():
    load_dotenv()
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = MarketMakerBot(settings)
    try:
        await bot.run()
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(bootstrap())