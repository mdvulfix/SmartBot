# === file: strategy.py ===

import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Any
from exchange import Exchange, Coin
from abc import ABC, abstractmethod

class Strategy(ABC):
    """Абстрактный класс торговой стратегии"""
    @abstractmethod
    def generate_signals(self, price: Decimal, position: Decimal) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_risk_parameters(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def update_market_data(self, data: Dict[str, Any]):
        pass
    
    @abstractmethod
    def should_cancel_order(self, order: Dict, current_signals: Dict) -> bool:
        """Должна ли стратегия отменить этот ордер?"""
        pass

class GridStrategy(Strategy):
    """Стратегия Grid Trading"""
    def __init__(
        self,
        coin: Coin,
        lower_bound: Decimal,
        upper_bound: Decimal,
        grid_levels: int,
        order_size: Decimal,
        max_orders: int = 10,
        position_size: Decimal = Decimal('0'),
        grid_spacing: str = 'arithmetic'
    ):
        self.coin = coin
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.grid_levels = grid_levels
        self.order_size = order_size
        self.max_orders = max_orders
        self.position_size = position_size
        self.grid_spacing = grid_spacing
        
        self.grid_prices: List[Decimal] = []
        self._generate_grid_prices()
        
        self.logger = logging.getLogger("grid_strategy")
        self.logger.info(f"GridStrategy initialized for {coin.symbol_id}")

    def _generate_grid_prices(self):
        """Генерация ценовых уровней сетки"""
        self.grid_prices = []
        
        if self.grid_spacing == 'geometric':
            ratio = (self.upper_bound / self.lower_bound) ** (1 / (self.grid_levels - 1))
            for i in range(self.grid_levels):
                price = self.lower_bound * (ratio ** i)
                self.grid_prices.append(price)
        else:
            step = (self.upper_bound - self.lower_bound) / (self.grid_levels - 1)
            for i in range(self.grid_levels):
                price = self.lower_bound + (step * i)
                self.grid_prices.append(price)
        
        # Округляем до 8 знаков для криптовалют
        self.grid_prices = [p.quantize(Decimal('0.00000000')) for p in self.grid_prices]

    def generate_signals(self, price: Decimal, position: Decimal) -> Dict[str, Any]:
        """Генерация торговых сигналов на основе сетки"""
        buy_levels = [p for p in self.grid_prices if p < price]
        sell_levels = [p for p in self.grid_prices if p > price]
        
        return {
            'buy_levels': buy_levels[-self.max_orders:],
            'sell_levels': sell_levels[:self.max_orders],
            'current_price': price,
            'position': position
        }

    def get_risk_parameters(self) -> Dict[str, Any]:
        """Возвращает параметры управления рисками"""
        return {
            'order_size': self.order_size,
            'max_orders': self.max_orders,
            'position_size': self.position_size
        }

    def update_market_data(self, data: Dict[str, Any]):
        """Обновление рыночных данных (для адаптивных стратегий)"""
        # Для базовой grid-стратегии не требуется адаптация
        pass

    def update_grid(self, lower: Decimal, upper: Decimal, levels: int):
        """Обновление параметров сетки"""
        self.lower_bound = lower
        self.upper_bound = upper
        self.grid_levels = levels
        self._generate_grid_prices()
        self.logger.info("Grid parameters updated")

class MeanReversionStrategy(Strategy):
    """Стратегия торговли по возврату к среднему"""
    def __init__(self, coin: Coin, window: int, std_dev: Decimal, order_size: Decimal):
        self.coin = coin
        self.window = window  # Период для расчета SMA
        self.std_dev = std_dev  # Количество стандартных отклонений
        self.order_size = order_size
        self.prices: List[Decimal] = []
        
    def update_market_data(self, data: Dict[str, Any]):
        """Обновление рыночных данных"""
        self.prices.append(data['price'])
        if len(self.prices) > self.window:
            self.prices.pop(0)
    
    def generate_signals(self, price: Decimal, position: Decimal) -> Dict[str, Any]:
        """Генерация сигналов на основе отклонения от среднего"""
        if len(self.prices) < self.window:
            return {'buy': False, 'sell': False}
        
        # Расчет SMA и стандартного отклонения
        sma = sum(self.prices) / len(self.prices)
        variance = sum((x - sma) ** 2 for x in self.prices) / len(self.prices)
        std = variance.sqrt()
        
        # Генерация сигналов
        buy_signal = price < sma - self.std_dev * std
        sell_signal = price > sma + self.std_dev * std
        
        return {
            'buy': buy_signal,
            'sell': sell_signal,
            'sma': sma,
            'std': std
        }
    
    def get_risk_parameters(self) -> Dict[str, Any]:
        return {'order_size': self.order_size}

class AdaptiveGridStrategy(GridStrategy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.performance_history = []
        self.adjustment_threshold = Decimal('0.05')  # 5% убытков
        
    def update_performance(self, performance: Dict[str, Any]):
        """Обновление параметров на основе производительности"""
        self.performance_history.append(performance)
        
        # Анализируем последние 10 сделок
        recent_trades = self.performance_history[-10:]
        if len(recent_trades) < 5:
            return
            
        total_profit = sum(Decimal(p['total_profit']) for p in recent_trades)
        
        # Если убыток превышает порог - адаптируем сетку
        if total_profit < 0 and abs(total_profit) > self.adjustment_threshold:
            self._adjust_grid_parameters()
            
    def _adjust_grid_parameters(self):
        """Адаптация параметров сетки"""
        # Увеличиваем диапазон при убытках
        price_range = self.upper_bound - self.lower_bound
        new_lower = self.lower_bound - price_range * Decimal('0.1')
        new_upper = self.upper_bound + price_range * Decimal('0.1')
        
        # Увеличиваем количество уровней
        new_levels = min(self.grid_levels + 2, 50)
        
        self.update_grid(new_lower, new_upper, new_levels)
        self.logger.info(f"Adjusted grid to {new_lower}-{new_upper} with {new_levels} levels")

class RiskAwareGridStrategy(GridStrategy):
    def __init__(self, *args, max_drawdown=Decimal('0.05'), **kwargs):
        super().__init__(*args, **kwargs)
        self.max_drawdown = max_drawdown  # 5% макс просадка
        
    def generate_signals(self, price: Decimal, position: Position) -> Dict[str, Any]:
        signals = super().generate_signals(price, position.current_size if position else Decimal('0'))
        
        # Анализ риска текущей позиции
        if position and position.status == PositionStatus.OPEN:
            # Рассчитываем просадку относительно максимальной прибыли
            current_drawdown = position.max_profit - (position.realized_pnl + position.unrealized_pnl)
            drawdown_percent = current_drawdown / position.entry_price / position.current_size
            
            # Если просадка превышает лимит - генерируем сигнал на снижение риска
            if drawdown_percent > self.max_drawdown:
                signals['risk_reduction'] = True
                # Добавляем дополнительные уровни продажи
                signals['sell_levels'] = signals['sell_levels'][:2]  # Оставляем только ближайшие уровни
            else:
                signals['risk_reduction'] = False
        
        return signals