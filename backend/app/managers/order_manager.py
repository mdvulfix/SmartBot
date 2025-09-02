####################
### execution/order_manager.py
####################

"""Управление жизненным циклом ордеров"""
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any
from decimal import Decimal

from models.order import Order, OrderStatus

class OrderManager:
    """Централизованное управление ордерами: создание, обновление, анализ"""
    def __init__(self):
        self.orders: Dict[str, Order] = {}
        self.orders_by_strategy = defaultdict(list)
        self.orders_by_coin = defaultdict(list)

    def create_order(
        self,
        order_id: str,
        side: str,
        price: Decimal,
        size: Decimal,
        coin: str,
        strategy: str
    ) -> Order:
        """Фабричный метод создания и регистрации ордера"""
        order = Order(order_id, side, price, size, coin, strategy)
        self.add_order(order)
        return order

    def add_order(self, order: Order):
        """Регистрация нового ордера в системе"""
        self.orders[order.id] = order
        self.orders_by_strategy[order.strategy].append(order.id)
        self.orders_by_coin[order.coin].append(order.id)

    def update_order_fill(
        self,
        order_id: str,
        filled_size: Decimal,
        filled_price: Decimal,
        fee: Decimal,
        fee_currency: str
    ):
        """Обновление информации о частичном/полном исполнении"""
        if order_id not in self.orders:
            return

        order = self.orders[order_id]
        status = OrderStatus.FILLED if filled_size >= order.size else OrderStatus.PARTIALLY_FILLED
        order.update_fill(filled_size, filled_price, fee, fee_currency, status)

        if status == OrderStatus.FILLED:
            self.close_order(order_id, "filled", OrderStatus.FILLED)

    def close_order(self, order_id: str, reason: str, status: OrderStatus = OrderStatus.CANCELED):
        """Закрытие ордера с указанием причины"""
        if order_id in self.orders:
            self.orders[order_id].close(reason, status)

    def get_order(self, order_id: str) -> Optional[Order]:
        """Получение ордера по ID"""
        return self.orders.get(order_id)

    def get_active_orders(self) -> List[Order]:
        """Все активные и частично исполненные ордера"""
        return [
            o for o in self.orders.values()
            if o.status in (OrderStatus.ACTIVE, OrderStatus.PARTIALLY_FILLED)
        ]

    def strategy_performance(self, strategy: str) -> Dict[str, Any]:
        """Анализ эффективности ордеров по стратегии (грубая оценка)"""
        orders = [o for o in self.orders.values() if o.strategy == strategy]
        if not orders:
            return {"total_orders": 0, "win_rate": 0.0, "total_profit": "0"}

        total_profit = Decimal("0")
        winning_orders = 0

        for order in orders:
            if order.filled_price is not None and order.filled_size > 0:
                # Простейшая эвристика (для реального PnL используйте Position)
                profit = (order.filled_price - order.price) * order.filled_size
                if order.side == "sell":
                    profit = -profit
                total_profit += profit
                if profit > 0:
                    winning_orders += 1

        win_rate = winning_orders / len(orders) if orders else 0.0
        return {
            "total_orders": len(orders),
            "win_rate": win_rate,
            "total_profit": str(total_profit)
        }
