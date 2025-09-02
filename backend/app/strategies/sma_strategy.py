# strategies/sma_strategy.py
from decimal import Decimal
from typing import Dict, Any, List
from collections import deque
from core.strategy import Strategy
from models.coin import Coin

class SmaStrategy(Strategy):
    """
    Простая стратегия: SMA crossover (fast/slow).
    На вход возвращает сигналы: buy_levels и sell_levels — по ним бэктестер разместит лимитные ордера.
    Для упрощения: мы используем уровень равный текущей close ± небольшая сетка.
    """
    def __init__(self, coin: Coin, fast: int = 20, slow: int = 50, order_size: Decimal = Decimal("0.001")):
        super().__init__(coin)
        self.fast = fast
        self.slow = slow
        self.order_size = order_size
        self.close_history = deque(maxlen=self.slow)
        self.last_signal = None  # 'long'/'short'/None

    def _sma(self, window: int) -> Decimal:
        if len(self.close_history) < window:
            return Decimal("0")
        arr = list(self.close_history)[-window:]
        s = sum(arr)
        return s / Decimal(len(arr))

    def generate_signals(self, price: Decimal, position: Any) -> Dict[str, Any]:
        # Передаём цену
        self.close_history.append(price)

        fast_sma = self._sma(self.fast)
        slow_sma = self._sma(self.slow)

        buy_levels: List[Decimal] = []
        sell_levels: List[Decimal] = []

        if fast_sma == 0 or slow_sma == 0:
            return {"buy_levels": [], "sell_levels": []}

        # crossover logic
        if fast_sma > slow_sma and self.last_signal != "long":
            # сигнал на покупку — разместим лимит чуть ниже рынка (buy dip)
            buy_levels = [price * (Decimal("1") - Decimal("0.002"))]  # 0.2% ниже
            self.last_signal = "long"
        elif fast_sma < slow_sma and self.last_signal != "short":
            # сигнал на продажу — лимит чуть выше рынка
            sell_levels = [price * (Decimal("1") + Decimal("0.002"))]  # 0.2% выше
            self.last_signal = "short"

        return {"buy_levels": buy_levels, "sell_levels": sell_levels}

    def get_risk_parameters(self) -> Dict[str, Any]:
        return {"order_size": self.order_size, "max_orders": 1}
