from __future__ import annotations

import asyncio
import signal
import structlog
import sys
import json
import time
from typing import Any
from dotenv import load_dotenv

from src.config import Settings, get_settings
from src.inventory.inventory_manager import InventoryManager
from src.logging_config import configure_logging
from src.market_maker.quote_engine import QuoteEngine
from src.market_maker.advanced_quote_engine import AdvancedQuoteEngine  # НОВОЕ
from src.market_discovery import MarketDiscovery
from src.polymarket.rest_client import PolymarketRestClient
from src.polymarket.websocket_orderbook import (
    PolymarketWebSocketOrderbook,
    OrderbookSnapshot,
)

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
            settings.target_inventory_balance,
        )
        self.quote_engine = AdvancedQuoteEngine(settings, self.inventory_manager)  # ОБНОВЛЕНО
        self.ws_orderbook = PolymarketWebSocketOrderbook()

        self.market_id: str | None = None
        self.tokens: list[str] = []

    async def initialize_market(self) -> bool:
        """Инициализация рынка. Пропускаем WS, если он не работает, работаем через REST."""
        m_id = self.settings.get_market_id()
        if not m_id:
            m_id = await self.market_discovery.interactive_market_selection(
                self.settings.min_volume_24h,
                self.settings.max_spread_bps,
            )

        if m_id:
            self.market_id = m_id
            try:
                info = await self.rest_client.get_market_info(m_id)
                raw_tokens = info.get("clobTokenIds", [])
                self.tokens = json.loads(raw_tokens) if isinstance(raw_tokens, str) else raw_tokens

                logger.info("market_initialized", id=self.market_id, question=info.get("question"))
                return True
            except Exception as e:
                logger.error("market_initialization_failed", error=str(e))
                return False
        return False

    async def update_loop(self) -> None:
        """
        Улучшенный цикл Spread Farming (REST Only).
        Реализовано: Anti-crossing, Parallel execution, Drift compensation.
        """
        if len(self.tokens) < 2:
            logger.error("insufficient_tokens")
            return

        yes_token, no_token = self.tokens[0], self.tokens[1]
        token_ids = [yes_token, no_token]

        logger.info("starting_spread_farming_loop", refresh_ms=self.settings.quote_refresh_rate_ms)

        while not self._stop_event.is_set():
            start_time = time.perf_counter()

            try:
                # 1. Получаем текущий стакан (REST)
                orderbook = await self.rest_client.get_orderbook(self.market_id, token_ids=token_ids)
                if not orderbook:
                    await asyncio.sleep(1)
                    continue

                bid = orderbook.get("best_bid", 0.0)
                ask = orderbook.get("best_ask", 1.0)

                # 2. Anti-Crossing Logic: Проверка, чтобы не стать тейкером
                # Если спред слишком узкий или отрицательный, раздвигаем котировки
                if bid >= ask:
                    logger.warning("anti_crossing_triggered", bid=bid, ask=ask)
                    bid -= 0.0001
                    ask += 0.0001

                # 3. Batch Cancellation: Отменяем все активные ордера в этом маркете перед обновлением
                # Это предотвращает "наслоение" старых цен на новые
                await self.rest_client.cancel_all_orders(self.market_id)

                # 4. Генерация новых котировок (Top-of-book logic внутри engine)
                yes_quote, no_quote = self.quote_engine.generate_advanced_quotes(
                    market_id=self.market_id,
                    mid_price=(bid + ask) / 2.0,
                    best_bid=bid,
                    best_ask=ask,
                    yes_token_id=yes_token,
                    no_token_id=no_token,
                    orderbook_data=orderbook,
                )

                # 5. Parallel Order Placement: Отправляем ордера одновременно
                tasks = []
                if yes_quote:
                    # Принудительно ставим флаг post_only в методе клиента (если реализовано)
                    tasks.append(self.rest_client.create_order(yes_quote))
                if no_quote:
                    tasks.append(self.rest_client.create_order(no_quote))

                if tasks:
                    # Используем gather для параллельной отправки HTTP-запросов
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, Exception):
                            logger.error("order_placement_failed", error=str(res))

                # 6. Drift Compensation: Вычисляем время сна так, чтобы цикл был ровно N мс
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                sleep_time = max(0, self.settings.quote_refresh_rate_ms - elapsed_ms)

                logger.info(
                    "cycle_complete",
                    bid=round(bid, 4),
                    ask=round(ask, 4),
                    work_ms=round(elapsed_ms, 1),
                    next_in=round(sleep_time, 1)
                )

                await asyncio.sleep(sleep_time / 1000.0)

            except Exception as e:
                logger.error("loop_error", error=str(e), exc_info=True)
                await asyncio.sleep(2)

    async def run(self) -> None:
        self.running = True
        if await self.initialize_market():
            await self.update_loop()

    async def stop(self) -> None:
        if not self.running: return
        logger.info("stopping_bot_gracefully")
        self._stop_event.set()
        self.running = False

        # Финальная отмена всех ордеров перед выходом
        try:
            if self.market_id:
                await self.rest_client.cancel_all_orders(self.market_id)
        except: pass

        await self.rest_client.close()
        await self.ws_orderbook.close()
        await self.market_discovery.close()

async def bootstrap() -> None:
    load_dotenv()
    settings = get_settings()
    configure_logging(settings.log_level)
    bot = MarketMakerBot(settings)

    try:
        await bot.run()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("shutdown_signal_received")
    finally:
        await bot.stop()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(bootstrap())
    except KeyboardInterrupt:
        sys.exit(0)