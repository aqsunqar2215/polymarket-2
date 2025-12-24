from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TradeRecord:
    """Информация об одной торговле (паре YES/NO)"""
    
    trade_id: str
    yes_order_id: str | None = None
    no_order_id: str | None = None
    
    # Entry информация
    yes_entry_price: float = 0.0
    no_entry_price: float = 0.0
    yes_size: float = 0.0
    no_size: float = 0.0
    entry_time: datetime = field(default_factory=datetime.now)
    
    # Exit информация
    yes_exit_price: float | None = None
    no_exit_price: float | None = None
    exit_time: datetime | None = None
    
    # P&L
    gross_pnl: float = 0.0
    fees: float = 0.0
    net_pnl: float = 0.0
    
    # Status
    is_closed: bool = False
    
    def calculate_pnl(self, current_yes_price: float) -> float:
        """Рассчитываем текущий P&L позиции."""
        yes_pnl = (current_yes_price - self.yes_entry_price) * self.yes_size
        no_pnl = ((1.0 - current_yes_price) - (1.0 - self.no_entry_price)) * self.no_size
        return yes_pnl + no_pnl
    
    def close_trade(self, yes_exit_price: float, no_exit_price: float, fees: float = 0.0):
        """Закрываем торговлю и рассчитываем финальный P&L."""
        self.yes_exit_price = yes_exit_price
        self.no_exit_price = no_exit_price
        self.exit_time = datetime.now()
        self.is_closed = True
        
        # P&L = (exit - entry) * size
        yes_pnl = (yes_exit_price - self.yes_entry_price) * self.yes_size
        no_pnl = (no_exit_price - self.no_entry_price) * self.no_size
        
        self.gross_pnl = yes_pnl + no_pnl
        self.fees = fees
        self.net_pnl = self.gross_pnl - fees


class ProfitTracker:
    """
    Отслеживает все торговли и рассчитывает P&L.
    """

    def __init__(self, market_id: str):
        self.market_id = market_id
        self.trades: dict[str, TradeRecord] = {}
        self.trade_counter = 0
        
        # Статистика
        self.total_gross_pnl = 0.0
        self.total_fees = 0.0
        self.total_net_pnl = 0.0
        self.closed_trades_count = 0
        self.open_trades_count = 0
        
        logger.info("profit_tracker_initialized", market_id=market_id)

    def create_trade(
        self,
        yes_order_id: str,
        no_order_id: str,
        yes_price: float,
        no_price: float,
        yes_size: float,
        no_size: float,
    ) -> str:
        """
        Создаем новую торговлю.
        
        Returns:
            trade_id для отслеживания
        """
        self.trade_counter += 1
        trade_id = f"trade_{self.market_id}_{self.trade_counter}"
        
        trade = TradeRecord(
            trade_id=trade_id,
            yes_order_id=yes_order_id,
            no_order_id=no_order_id,
            yes_entry_price=yes_price,
            no_entry_price=no_price,
            yes_size=yes_size,
            no_size=no_size,
        )
        
        self.trades[trade_id] = trade
        self.open_trades_count += 1
        
        logger.info(
            "trade_created",
            trade_id=trade_id,
            yes_price=round(yes_price, 6),
            no_price=round(no_price, 6),
            yes_size=round(yes_size, 2),
            no_size=round(no_size, 2),
        )
        
        return trade_id

    def close_trade(
        self,
        trade_id: str,
        yes_exit_price: float,
        no_exit_price: float,
        fees: float = 0.0,
    ) -> bool:
        """
        Закрываем торговлю и рассчитываем P&L.
        
        Returns:
            True если успешно закрыли
        """
        if trade_id not in self.trades:
            logger.warning("trade_not_found", trade_id=trade_id)
            return False
        
        trade = self.trades[trade_id]
        trade.close_trade(yes_exit_price, no_exit_price, fees)
        
        # Обновляем статистику
        self.total_gross_pnl += trade.gross_pnl
        self.total_fees += fees
        self.total_net_pnl += trade.net_pnl
        self.open_trades_count -= 1
        self.closed_trades_count += 1
        
        # Логируем результат
        pnl_status = "PROFIT ✅" if trade.net_pnl > 0 else "LOSS ❌" if trade.net_pnl < 0 else "BREAK-EVEN"
        
        logger.info(
            "trade_closed",
            trade_id=trade_id,
            yes_exit_price=round(yes_exit_price, 6),
            no_exit_price=round(no_exit_price, 6),
            gross_pnl=round(trade.gross_pnl, 4),
            fees=round(fees, 4),
            net_pnl=round(trade.net_pnl, 4),
            status=pnl_status,
        )
        
        return True

    def get_trade(self, trade_id: str) -> TradeRecord | None:
        """Получить информацию о торговле."""
        return self.trades.get(trade_id)

    def get_unrealized_pnl(self, current_yes_price: float) -> float:
        """
        Рассчитываем нереализованный P&L для открытых позиций.
        """
        unrealized = 0.0
        
        for trade in self.trades.values():
            if not trade.is_closed:
                unrealized += trade.calculate_pnl(current_yes_price)
        
        return unrealized

    def get_statistics(self, current_yes_price: float) -> dict[str, Any]:
        """
        Получить полную статистику по торговле.
        """
        unrealized_pnl = self.get_unrealized_pnl(current_yes_price)
        total_pnl = self.total_net_pnl + unrealized_pnl
        
        return {
            "market_id": self.market_id,
            "closed_trades": self.closed_trades_count,
            "open_trades": self.open_trades_count,
            "realized_pnl": round(self.total_net_pnl, 4),
            "unrealized_pnl": round(unrealized_pnl, 4),
            "total_pnl": round(total_pnl, 4),
            "total_gross_pnl": round(self.total_gross_pnl, 4),
            "total_fees": round(self.total_fees, 4),
            "win_rate": (
                round(
                    len([t for t in self.trades.values() if t.is_closed and t.net_pnl > 0])
                    / self.closed_trades_count
                    * 100,
                    2,
                )
                if self.closed_trades_count > 0
                else 0
            ),
        }

    def log_statistics(self, current_yes_price: float):
        """Логируем текущую статистику."""
        stats = self.get_statistics(current_yes_price)
        
        logger.info(
            "trading_statistics",
            closed_trades=stats["closed_trades"],
            open_trades=stats["open_trades"],
            realized_pnl=stats["realized_pnl"],
            unrealized_pnl=stats["unrealized_pnl"],
            total_pnl=stats["total_pnl"],
            win_rate=stats["win_rate"],
        )

    def get_summary(self) -> str:
        """
        Возвращает текстовый summary всех торговель.
        """
        stats = self.get_statistics(0.5)  # Assume mid price
        
        summary = f"""
╔═══════════════════════════════════════════════════════╗
║          📊 TRADING SUMMARY                           ║
╚═══════════════════════════════════════════════════════╝

Market: {stats['market_id']}

Trades:
  Closed: {stats['closed_trades']}
  Open:   {stats['open_trades']}

P&L:
  Realized:    ${stats['realized_pnl']:>10.4f}
  Unrealized:  ${stats['unrealized_pnl']:>10.4f}
  Total:       ${stats['total_pnl']:>10.4f}

Fees:        ${stats['total_fees']:>10.4f}
Gross P&L:   ${stats['total_gross_pnl']:>10.4f}

Win Rate:    {stats['win_rate']:>10.2f}%

╚═══════════════════════════════════════════════════════╝
        """
        
        return summary