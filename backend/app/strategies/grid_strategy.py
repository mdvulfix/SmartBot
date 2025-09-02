####################
### strategies/grid_strategy.py
####################

"""Стратегия сеточной торговли"""
from decimal import Decimal
from typing import Dict, List, Any

from core.strategy import Strategy
from core.exceptions import StrategyError
from models.coin import Coin

class GridStrategy(Strategy):
    """
    Стратегия размещения ордеров по сетке цен.
    """
    def __init__(
        self,
        coin: Coin,
        lower_bound: Decimal,
        upper_bound: Decimal,
        grid_levels: int,
        order_size: Decimal,
        max_orders: int = 10,
        grid_spacing: str = "arithmetic"
    ):
        super().__init__(coin)
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.grid_levels = grid_levels
        self.order_size = order_size
        self.max_orders = max_orders
        self.grid_spacing = grid_spacing

        self.validate_parameters()
        self.generate_grid()

    def validate_parameters(self):
        if self.lower_bound >= self.upper_bound:
            raise StrategyError("Lower bound must be less than upper bound")
        if self.grid_levels < 3:
            raise StrategyError("At least 3 grid levels required")
        if self.order_size <= 0:
            raise StrategyError("Order size must be positive")

    def generate_grid(self):
        self.grid_prices: List[Decimal] = []

        if self.grid_spacing == "geometric":
            exponent = Decimal("1") / Decimal(str(self.grid_levels - 1))
            ratio = (self.upper_bound / self.lower_bound) ** exponent
            for i in range(self.grid_levels):
                price = self.lower_bound * (ratio ** i)
                self.grid_prices.append(price)
        else:
            step = (self.upper_bound - self.lower_bound) / (self.grid_levels - 1)
            for i in range(self.grid_levels):
                price = self.lower_bound + (step * i)
                self.grid_prices.append(price)

        self.grid_prices = [p.quantize(Decimal("0.00000000")) for p in self.grid_prices]

    def generate_signals(self, price: Decimal, position: Any) -> Dict[str, Any]:
        buy_levels = [p for p in self.grid_prices if p < price]
        sell_levels = [p for p in self.grid_prices if p > price]
        return {
            "buy_levels": buy_levels[-self.max_orders:],
            "sell_levels": sell_levels[:self.max_orders],
        }

    def get_risk_parameters(self) -> Dict[str, Any]:
        return {
            "order_size": self.order_size,
            "max_orders": self.max_orders
        }

    def update_grid(self, lower: Decimal, upper: Decimal, levels: int):
        self.lower_bound = lower
        self.upper_bound = upper
        self.grid_levels = levels
        self.validate_parameters()
        self.generate_grid()
