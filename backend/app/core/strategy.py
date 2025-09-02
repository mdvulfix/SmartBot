####################
### core/strategy.py
####################

"""Базовый класс и интерфейсы для торговых стратегий"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict

from models.coin import Coin
from core.exceptions import StrategyError

class Strategy(ABC):
    """Абстрактный базовый класс для всех стратегий"""
    def __init__(self, coin: Coin):
        self.coin = coin

    @abstractmethod
    def generate_signals(self, price: Decimal, position: Any) -> Dict[str, Any]:
        """Генерация торговых сигналов на основе текущей ситуации"""
        raise NotImplementedError

    @abstractmethod
    def get_risk_parameters(self) -> Dict[str, Any]:
        """Параметры управления рисками для стратегии"""
        raise NotImplementedError

    def validate_parameters(self):
        """Валидация параметров стратегии (реализуется в наследниках)"""
        pass
