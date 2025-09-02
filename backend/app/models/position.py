####################
### models/position.py
####################

"""Управление торговой позицией"""
from enum import Enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional

class PositionStatus(Enum):
    """Состояния позиции"""
    OPEN = "open"
    CLOSED = "closed"

class Position:
    """Агрегированная информация о торговой позиции"""
    def __init__(self, id: str, coin: str, strategy: str, size: Decimal, price: Decimal):
        # Идентификаторы
        self.id = id
        self.coin = coin
        self.strategy = strategy

        # Параметры позиции
        self.status = PositionStatus.OPEN
        self.current_size = size
        self.entry_price = price
        self.current_price = price

        # Финансовые метрики
        self.realized_pnl = Decimal("0")     # Зафиксированная прибыль/убыток
        self.unrealized_pnl = Decimal("0")   # Незафиксированная прибыль/убыток
        self.total_fees = Decimal("0")       # Суммарные комиссии

        # Трекинг
        self.orders: List[str] = []          # Связанные ордера
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

        # Аналитика
        self.max_profit = Decimal("0")       # Максимальная достигнутая прибыль
        self.max_drawdown = Decimal("0")     # Максимальная просадка

    def add_order(self, order_id: str, size: Decimal, price: Decimal, fee: Decimal):
        """Добавляет ордер к позиции и пересчитывает метрики.
        size > 0 для покупки (увеличение), size < 0 для продажи (снижение).
        """
        self.orders.append(order_id)
        self.updated_at = datetime.now(timezone.utc)
        self.total_fees += fee

        if size > 0:
            # Усреднение входа
            total_cost = (self.current_size * self.entry_price) + (size * price)
            self.current_size += size
            if self.current_size != 0:
                self.entry_price = total_cost / self.current_size
            else:
                self.entry_price = price
        else:
            # Фиксация части прибыли при продаже
            realized_size = min(-size, self.current_size)
            self.realized_pnl += realized_size * (price - self.entry_price)
            self.current_size -= realized_size

            if self.current_size <= Decimal("0.00000001"):
                self.close()

        self.calculate_pnl()

    def update_price(self, price: Decimal):
        """Обновляет текущую рыночную цену и пересчитывает PnL"""
        self.current_price = price
        self.updated_at = datetime.now(timezone.utc)
        self.calculate_pnl()

    def calculate_pnl(self):
        """Пересчитывает реализованный и нереализованный PnL"""
        if self.current_size > 0:
            self.unrealized_pnl = self.current_size * (self.current_price - self.entry_price)
        else:
            self.unrealized_pnl = Decimal("0")

        total_pnl = self.realized_pnl + self.unrealized_pnl
        if total_pnl > self.max_profit:
            self.max_profit = total_pnl
        dd = self.max_profit - total_pnl
        if dd > self.max_drawdown:
            self.max_drawdown = dd

    def close(self):
        """Окончательное закрытие позиции"""
        if self.status == PositionStatus.OPEN:
            self.status = PositionStatus.CLOSED
            self.updated_at = datetime.now(timezone.utc)
            self.realized_pnl += self.unrealized_pnl
            self.unrealized_pnl = Decimal("0")

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь для отчетов"""
        return {
            "id": self.id,
            "coin": self.coin,
            "strategy": self.strategy,
            "status": self.status.value,
            "size": str(self.current_size),
            "entry_price": str(self.entry_price),
            "current_price": str(self.current_price),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "total_fees": str(self.total_fees),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

class PositionFactory:
    @staticmethod
    def create_from_bot_state(coin: str, size: Decimal, price: Decimal) -> Position:
        position_id = f"pos-{coin}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        strategy = "DefaultStrategy"
        return Position(position_id, coin, strategy, size, price)
