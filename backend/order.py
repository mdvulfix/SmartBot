# === file: order.py ===

from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

class OrderStatus(Enum):
    ACTIVE = "active"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"

class Order:
    def __init__(self, order_id: str, side: str, price: Decimal, size: Decimal, coin: str, strategy: str, created_at: Optional[datetime] = None):
        self._id = order_id
        self._side = side
        self.price = price
        self.size = size
        self.coin = coin
        
        self.strategy = strategy
        self.created_at = created_at or datetime.now(datetime.timezone.utc)
        self.updated_at = self.created_at
        self.status = OrderStatus.ACTIVE
        self.filled_at: Optional[datetime] = None
        self.filled_price: Optional[Decimal] = None
        self.filled_size: Decimal = Decimal('0')
        self.fee: Decimal = Decimal('0')
        self.fee_currency: Optional[str] = None
        self.profit: Optional[Decimal] = None
        self.close_reason: Optional[str] = None

    def update_fill(self, filled_size: Decimal, filled_price: Decimal, fee: Decimal, fee_currency: str, status: OrderStatus):
        self.status = status
        self.updated_at = datetime.now(datetime.timezone.utc)
        self.filled_size = filled_size
        self.filled_price = filled_price
        self.fee = fee
        self.fee_currency = fee_currency
        
        if status == OrderStatus.FILLED:
            self.filled_at = self.updated_at

    def calculate_profit(self, exit_price: Optional[Decimal] = None):
        if self._side == 'buy' and exit_price:
            self.profit = (exit_price - self.filled_price) * self.filled_size - self.fee
        return self.profit

    def close(self, reason: str, status: OrderStatus = OrderStatus.CANCELED):
        self.status = status
        self.updated_at = datetime.now(datetime.timezone.utc)
        self.close_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self._id,
            "side": self._side,
            "price": str(self.price),
            "size": str(self.size),
            "coin": self.coin,
            "strategy": self.strategy,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "filled_price": str(self.filled_price) if self.filled_price else None,
            "filled_size": str(self.filled_size),
            "fee": str(self.fee),
            "fee_currency": self.fee_currency,
            "profit": str(self.profit) if self.profit is not None else None,
            "close_reason": self.close_reason
        }
    
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

class OrderManager:
    def __init__(self):
        self.active_orders: Dict[str, Order] = {}
        self.closed_orders: Dict[str, Order] = {}
        self.orders_by_strategy = defaultdict(list)
        self.orders_by_coin = defaultdict(list)

    def add_order(self, order: Order):
        self.active_orders[order._id] = order
        self.orders_by_strategy[order.strategy].append(order._id)
        self.orders_by_coin[order.coin].append(order._id)

    def update_order_fill(self, order_id: str, filled_size: Decimal, filled_price: Decimal, fee: Decimal, fee_currency: str, status: OrderStatus = OrderStatus.FILLED):
        if order_id in self.active_orders:
            order = self.active_orders[order_id]
            order.update_fill(filled_size, filled_price, fee, fee_currency,status)
            
            if status in {OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED}:
                # Для частичного исполнения ордер остается активным
                if status == OrderStatus.FILLED:
                    self._move_to_closed(order_id)
            else:
                self._move_to_closed(order_id)

    def close_order(self, order_id: str, reason: str, status: OrderStatus = OrderStatus.CANCELED):
        if order_id in self.active_orders:
            order = self.active_orders[order_id]
            order.close(reason, status)
            self._move_to_closed(order_id)

    def _move_to_closed(self, order_id: str):
        if order_id in self.active_orders:
            order = self.active_orders.pop(order_id)
            self.closed_orders[order_id] = order

    def get_order(self, order_id: str) -> Optional[Order]:
        if order_id in self.active_orders:
            return self.active_orders[order_id]
        return self.closed_orders.get(order_id)

    def get_active_orders(self) -> List[Order]:
        return list(self.active_orders.values())

    def get_closed_orders(self) -> List[Order]:
        return list(self.closed_orders.values())

    def get_orders_by_strategy(self, strategy: str) -> Tuple[List[Order], List[Order]]:
        active = []
        closed = []
        for order_id in self.orders_by_strategy.get(strategy, []):
            if order_id in self.active_orders:
                active.append(self.active_orders[order_id])
            elif order_id in self.closed_orders:
                closed.append(self.closed_orders[order_id])
        return active, closed

    def get_orders_by_coin(self, coin: str) -> Tuple[List[Order], List[Order]]:
        active = []
        closed = []
        for order_id in self.orders_by_coin.get(coin, []):
            if order_id in self.active_orders:
                active.append(self.active_orders[order_id])
            elif order_id in self.closed_orders:
                closed.append(self.closed_orders[order_id])
        return active, closed

    def calculate_strategy_performance(self, strategy: str) -> Dict[str, Any]:
        _, closed_orders = self.get_orders_by_strategy(strategy)
        return self._analyze_orders(closed_orders)

    def calculate_coin_performance(self, coin: str) -> Dict[str, Any]:
        _, closed_orders = self.get_orders_by_coin(coin)
        return self._analyze_orders(closed_orders)

    def _analyze_orders(self, orders: List[Order]) -> Dict[str, Any]:
        if not orders:
            return {}
        
        # Рассчитываем метрики производительности
        total_profit = Decimal('0')
        winning_trades = 0
        losing_trades = 0
        buy_orders = 0
        sell_orders = 0
        
        for order in orders:
            if order.profit is not None:
                total_profit += order.profit
                if order.profit > 0:
                    winning_trades += 1
                elif order.profit < 0:
                    losing_trades += 1
                    
            if order._side == 'buy':
                buy_orders += 1
            else:
                sell_orders += 1
        
        total_trades = len(orders)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        return {
            "total_orders": total_trades,
            "buy_orders": buy_orders,
            "sell_orders": sell_orders,
            "win_rate": win_rate,
            "total_profit": str(total_profit),
            "average_profit": str(total_profit / total_trades) if total_trades > 0 else "0",
            "profit_factor": winning_trades / losing_trades if losing_trades > 0 else float('inf')
        }