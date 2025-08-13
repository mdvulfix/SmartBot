####################
### models/order.py
####################

"""Представление торгового ордера"""

from enum import Enum
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional

from core.exceptions import ExchangeError

class OrderStatus(Enum):
    """Жизненный цикл ордера"""
    ACTIVE = "active"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    REJECTED = "rejected"

class Order:
    """Детализированная информация о торговом ордере"""
    def __init__(
        self,
        id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        coin: str,
        strategy: str,
        created_at: Optional[datetime] = None
    ):
        # Идентификаторы
        self.id = id
        self.coin = coin
        self.strategy = strategy

        # Параметры ордера
        self.side = side.lower()  # buy/sell
        self.price = price
        self.size = size

        # Статус и время
        self.status = OrderStatus.ACTIVE
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = self.created_at

        # Исполнение ордера
        self.filled_size = Decimal("0")
        self.filled_price: Optional[Decimal] = None
        self.fee = Decimal("0")
        self.fee_currency: Optional[str] = None
        self.close_reason: Optional[str] = None

    def update_fill(
        self,
        filled_size: Decimal,
        filled_price: Decimal,
        fee: Decimal,
        fee_currency: str,
        status: OrderStatus
    ):
        """Обновляет информацию о частичном или полном исполнении"""
        self.filled_size = filled_size
        self.filled_price = filled_price
        self.fee = fee
        self.fee_currency = fee_currency
        self.status = status
        self.updated_at = datetime.now(timezone.utc)

    def close(self, reason: str, status: OrderStatus = OrderStatus.CANCELED):
        """Закрывает ордер (отмена/исполнение)"""
        self.status = status
        self.updated_at = datetime.now(timezone.utc)
        self.close_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь для отчетов"""
        return {
            "id": self.id,
            "side": self.side,
            "price": str(self.price),
            "size": str(self.size),
            "coin": self.coin,
            "status": self.status.value,
            "filled_size": str(self.filled_size),
            "filled_price": str(self.filled_price) if self.filled_price is not None else None,
            "fee": str(self.fee),
            "fee_currency": self.fee_currency,
            "close_reason": self.close_reason
        }

class OrderFactory:
    @staticmethod
    def _safe_decimal(val: Any, default: str = "0") -> Decimal:
        try:
            if val is None:
                return Decimal(default)
            return Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal(default)

    @staticmethod
    def create_from_exchange(data: dict) -> "Order":
        try:
            return Order(
                id=str(data.get("id", "")),
                side=str(data.get("side", "")),
                price=OrderFactory._safe_decimal(data.get("price", "0")),
                size=OrderFactory._safe_decimal(data.get("size", "0")),
                coin=str(data.get("coin", "")),
                strategy=str(data.get("strategy", "")),
                created_at=data.get("created_at")
            )
        except Exception as e:
            raise ExchangeError(f"Failed to create Order from exchange data: {e}")
