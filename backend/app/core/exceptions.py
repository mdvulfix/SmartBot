####################
### core/exceptions.py
####################
"""Кастомные исключения для торговой системы"""
class TradingException(Exception):
    """Базовый класс исключений для торговой системы"""

class ExchangeError(TradingException):
    """Ошибки взаимодействия с биржей (сеть, API)"""

class StrategyError(TradingException):
    """Некорректные параметры или логика стратегии"""

class RiskManagementError(TradingException):
    """Нарушение правил риск-менеджмента"""

class ConfigurationError(TradingException):
    """Проблемы с конфигурацией приложения"""