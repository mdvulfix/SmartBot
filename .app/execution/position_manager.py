####################
### execution/position_manager.py
####################

"""Управление торговыми позициями"""
from collections import defaultdict
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime, timezone

from models.position import Position, PositionStatus

class PositionManager:
    """Создание, обновление и анализ торговых позиций"""
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.positions_by_strategy = defaultdict(list)
        self.position_counter = 0

    def open_position(
        self,
        coin: str,
        strategy: str,
        size: Decimal,
        entry_price: Decimal
    ) -> Position:
        """Создание новой позиции"""
        position_id = f"pos-{self.position_counter}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        self.position_counter += 1

        position = Position(position_id, coin, strategy, size, entry_price)
        self.positions[position_id] = position
        self.positions_by_strategy[strategy].append(position_id)
        return position

    def add_order_to_position(
        self,
        position_id: str,
        order_id: str,
        side: str,
        size: Decimal,
        price: Decimal,
        fee: Decimal
    ):
        """Привязка ордера к позиции и обновление метрик"""
        if position_id not in self.positions:
            return

        position = self.positions[position_id]
        adjusted_size = size if side.lower() == "buy" else -size
        position.add_order(order_id, adjusted_size, price, fee)

        if position.status == PositionStatus.CLOSED:
            self.close_position(position_id)

    def close_position(self, position_id: str):
        """Принудительное закрытие позиции"""
        if position_id in self.positions:
            self.positions[position_id].close()

    def get_position(self, position_id: str) -> Optional[Position]:
        """Получение позиции по ID"""
        return self.positions.get(position_id)

    def get_position_for_order(self, order_id: str) -> Optional[Position]:
        """Поиск позиции по ID ордера"""
        for position in self.positions.values():
            if order_id in position.orders:
                return position
        return None

    def strategy_performance(self, strategy: str) -> Dict[str, Any]:
        """Анализ эффективности позиций по стратегии"""
        positions = [p for p in self.positions.values() if p.strategy == strategy]
        if not positions:
            return {"total_positions": 0, "win_rate": 0.0, "total_profit": "0"}

        total_profit = Decimal("0")
        winning_positions = 0

        for pos in positions:
            pnl = pos.realized_pnl + pos.unrealized_pnl
            total_profit += pnl
            if pnl > 0:
                winning_positions += 1

        win_rate = winning_positions / len(positions) if positions else 0.0
        return {
            "total_positions": len(positions),
            "win_rate": win_rate,
            "total_profit": str(total_profit)
        }
