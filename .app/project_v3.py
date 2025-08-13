####################
### utils/logger.py
####################
"""Настройка логгера для всего проекта"""
import logging
from logging.handlers import RotatingFileHandler

def get_logger(name: str) -> logging.Logger:
    """Создает и настраивает логгер с консольным и файловым выводом"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Формат сообщений: время-уровень-имя-сообщение
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # Консольный вывод
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    # Ротация логов (5 МБ, 3 файла)
    file_handler = RotatingFileHandler(f"{name}.log", maxBytes=5*1024*1024, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


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


####################
### models/coin.py
####################
"""Представление торгового инструмента (монеты)"""
from dataclasses import dataclass

@dataclass(frozen=True)  # Неизменяемый объект
class Coin:
    """Криптовалюта с методами для работы на бирже OKX"""
    symbol: str  # Базовый символ (BTC, ETH и т.д.)
    
    @property
    def symbol_id(self) -> str:
        """Форматированный ID для запросов к API OKX"""
        return f"{self.symbol}-USDT-SWAP" if self.symbol != "USDT" else "USDT"
    
    def __str__(self):
        return self.symbol


####################
### models/order.py
####################
"""Представление торгового ордера"""
from enum import Enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional

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
        self.side = side  # buy/sell
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
            "filled_price": str(self.filled_price) if self.filled_price else None,
            "fee": str(self.fee),
            "fee_currency": self.fee_currency,
            "close_reason": self.close_reason
        }

class OrderFactory:
    @staticmethod
    def create_from_exchange(data: dict) -> Order:
        # Example implementation: parse data dict and create Order
        try:
            return Order(
                id=data.get("id", ""),
                side=data.get("side", ""),
                price=Decimal(data.get("price", "0")),
                size=Decimal(data.get("size", "0")),
                coin=data.get("coin", ""),
                strategy=data.get("strategy", ""),
                created_at=data.get("created_at")
            )
        except Exception as e:
            raise ExchangeError(f"Failed to create Order from exchange data: {e}")


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

@dataclass
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
        self.realized_pnl = Decimal("0")  # Зафиксированная прибыль/убыток
        self.unrealized_pnl = Decimal("0")  # Незафиксированная прибыль/убыток
        self.total_fees = Decimal("0")  # Суммарные комиссии
        
        # Трекинг
        self.orders: List[str] = []  # Связанные ордера
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        
        # Аналитика
        self.max_profit = Decimal("0")  # Максимальная достигнутая прибыль
        self.max_drawdown = Decimal("0")  # Максимальная просадка

    def add_order(self, order_id: str, size: Decimal, price: Decimal, fee: Decimal):
        """Добавляет ордер к позиции и пересчитывает метрики"""
        self.orders.append(order_id)
        self.updated_at = datetime.now(timezone.utc)
        self.total_fees += fee
        
        # Для ордеров на покупку увеличиваем позицию
        if size > 0:
            # Пересчет средней цены входа
            total_cost = (self.current_size * self.entry_price) + (size * price)
            self.current_size += size
            self.entry_price = total_cost / self.current_size
        else:  # Ордера на продажу
            # Фиксируем часть прибыли
            realized_size = min(-size, self.current_size)
            self.realized_pnl += realized_size * (price - self.entry_price)
            self.current_size -= realized_size
            
            # Закрытие позиции при полной продаже
            if self.current_size <= Decimal("0.0001"):
                self.close()
        
        self.calculate_pnl()

    def update_price(self, price: Decimal):
        """Обновляет текущую рыночную цену и пересчитывает PnL"""
        self.current_price = price
        self.updated_at = datetime.now(timezone.utc)
        self.calculate_pnl()

    def calculate_pnl(self):
        """Пересчитывает реализованный и нереализованный PnL"""
        # Нереализованный PnL = текущая стоимость - стоимость входа
        if self.current_size > 0:
            self.unrealized_pnl = self.current_size * (self.current_price - self.entry_price)
        
        # Общий PnL для анализа экстремумов
        total_pnl = self.realized_pnl + self.unrealized_pnl
        self.max_profit = max(self.max_profit, total_pnl)
        self.max_drawdown = max(self.max_drawdown, self.max_profit - total_pnl)

    def close(self):
        """Окончательное закрытие позиции"""
        if self.status == PositionStatus.OPEN:
            self.status = PositionStatus.CLOSED
            self.updated_at = datetime.now(timezone.utc)
            # Фиксируем весь PnL
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
        # Generate a unique ID for the position (could be improved for real use)
        position_id = f"pos-{coin}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        # For demonstration, use a default strategy name
        strategy = "DefaultStrategy"
        return Position(position_id, coin, strategy, size, price)
       
####################
### execution/order_manager.py
####################
"""Управление жизненным циклом ордеров"""
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from decimal import Decimal

class OrderManager:
    """Централизованное управление ордерами: создание, обновление, анализ"""
    def __init__(self):
        # Хранилища данных
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
        status = OrderStatus.FILLED if filled_size == order.size else OrderStatus.PARTIALLY_FILLED
        order.update_fill(filled_size, filled_price, fee, fee_currency, status)
        
        if status == OrderStatus.FILLED:
            self.close_order(order_id, "filled")

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
        """Анализ эффективности ордеров по стратегии"""
        orders = [o for o in self.orders.values() if o.strategy == strategy]
        if not orders:
            return {}
            
        # Расчет метрик производительности
        total_profit = Decimal("0")
        winning_orders = 0
        
        for order in orders:
            if order.filled_price:
                # Прибыль = (цена исполнения - цена ордера) * размер
                # Для продаж: (ордер - исполнение) * размер
                profit = (order.filled_price - order.price) * order.filled_size
                if order.side == "sell":
                    profit = -profit
                    
                total_profit += profit
                if profit > 0:
                    winning_orders += 1
        
        return {
            "total_orders": len(orders),
            "win_rate": winning_orders / len(orders) if orders else 0,
            "total_profit": str(total_profit)
        }


####################
### execution/position_manager.py
####################
"""Управление торговыми позициями"""
from collections import defaultdict
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timezone

class PositionManager:
    """Создание, обновление и анализ торговых позиций"""
    def __init__(self):
        # Хранилища данных
        self.positions: Dict[str, Position] = {}
        self.positions_by_strategy = defaultdict(list)
        self.position_counter = 0  # Генератор уникальных ID

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
        # Размер отрицательный для ордеров на продажу
        adjusted_size = size if side == "buy" else -size
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
            return {}
            
        # Расчет метрик производительности
        total_profit = Decimal("0")
        winning_positions = 0
        
        for pos in positions:
            pnl = pos.realized_pnl + pos.unrealized_pnl
            total_profit += pnl
            if pnl > 0:
                winning_positions += 1
        
        return {
            "total_positions": len(positions),
            "win_rate": winning_positions / len(positions) if positions else 0,
            "total_profit": str(total_profit)
        }


####################
### core/strategy.py
####################
"""Базовый класс и интерфейсы для торговых стратегий"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict

class Strategy(ABC):
    """Абстрактный базовый класс для всех стратегий"""
    def __init__(self, coin: Coin):
        self.coin = coin
        
    @abstractmethod
    def generate_signals(self, price: Decimal, position: Any) -> Dict[str, Any]:
        """Генерация торговых сигналов на основе текущей ситуации"""
        pass
    
    @abstractmethod
    def get_risk_parameters(self) -> Dict[str, Any]:
        """Параметры управления рисками для стратегии"""
        pass
    
    def validate_parameters(self):
        """Валидация параметров стратегии (реализуется в наследниках)"""
        pass


####################
### strategies/grid_strategy.py
####################
"""Стратегия сеточной торговли"""
from decimal import Decimal
from typing import Dict, List, Any

class GridStrategy(Strategy):
    """
    Стратегия размещения ордеров по сетке цен.
    Особенности:
    - Равномерное распределение ордеров в ценовом диапазоне
    - Автоматическая адаптация под текущую цену
    - Управление размером позиции
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
        
        # Валидация параметров
        self.validate_parameters()
        # Генерация сетки цен
        self.generate_grid()

    def validate_parameters(self):
        """Проверка корректности входных параметров"""
        if self.lower_bound >= self.upper_bound:
            raise StrategyError("Lower bound must be less than upper bound")
        if self.grid_levels < 3:
            raise StrategyError("At least 3 grid levels required")
        if self.order_size <= 0:
            raise StrategyError("Order size must be positive")

    def generate_grid(self):
        """Генерация ценовых уровней сетки"""
        self.grid_prices = []
        
        # Геометрическая сетка (экспоненциальная)
        if self.grid_spacing == "geometric":
            exponent = Decimal("1") / Decimal(str(self.grid_levels - 1))
            ratio = (self.upper_bound / self.lower_bound) ** exponent
            for i in range(self.grid_levels):
                price = self.lower_bound * (ratio ** i)
                self.grid_prices.append(price)
        # Арифметическая сетка (линейная) по умолчанию
        else:
            step = (self.upper_bound - self.lower_bound) / (self.grid_levels - 1)
            for i in range(self.grid_levels):
                price = self.lower_bound + (step * i)
                self.grid_prices.append(price)
        
        # Округление до 8 знаков
        self.grid_prices = [p.quantize(Decimal("0.00000000")) for p in self.grid_prices]

    def generate_signals(self, price: Decimal, position: Any) -> Dict[str, Any]:
        """Генерация сигналов для размещения ордеров"""
        # Цены для покупки ниже текущей
        buy_levels = [p for p in self.grid_prices if p < price]
        # Цены для продажи выше текущей
        sell_levels = [p for p in self.grid_prices if p > price]
        
        return {
            "buy_levels": buy_levels[-self.max_orders:],  # Ближайшие к цене
            "sell_levels": sell_levels[:self.max_orders],  # Ближайшие к цене
        }

    def get_risk_parameters(self) -> Dict[str, Any]:
        """Параметры управления рисками"""
        return {
            "order_size": self.order_size,
            "max_orders": self.max_orders
        }

    def update_grid(self, lower: Decimal, upper: Decimal, levels: int):
        """Динамическое обновление параметров сетки"""
        self.lower_bound = lower
        self.upper_bound = upper
        self.grid_levels = levels
        self.validate_parameters()
        self.generate_grid()


####################
### core/exchange.py
####################
"""Интерфейс взаимодействия с биржей OKX"""
import hmac
import hashlib
import base64
import json
import asyncio
import aiohttp
from enum import Enum, auto
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict, Tuple
from aiohttp import ClientSession, ClientTimeout

class ExchangeState(Enum):
    """Состояния подключения к бирже"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ACTIVE = auto()        # Готов к торговле
    RATE_LIMITED = auto()  # Превышен лимит запросов
    BALANCE_LOW = auto()   # Недостаточный баланс
    API_ERROR = auto()     # Ошибки API
    NETWORK_ERROR = auto() # Проблемы сети

class Exchange(ABC):
    """Абстрактный интерфейс для работы с биржей"""
    @abstractmethod
    async def connect(self) -> bool:
        pass

    @abstractmethod
    async def get_balance(self, coin: Coin) -> Optional[Decimal]:
        pass

    @abstractmethod
    async def get_symbol_price(self, coin: Coin) -> Decimal:
        pass

    @abstractmethod
    async def place_limit_order(self, coin: Coin, side: str, price: Decimal, size: Decimal) -> Optional[str]:
        pass

    @abstractmethod
    async def get_open_orders(self, coin: Coin) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def cancel_order(self, coin: Coin, order_id: str) -> bool:
        pass

    @abstractmethod
    async def get_status_report(self) -> Dict[str, Any]:
        pass

class OkxExchange(Exchange):
    """Реализация взаимодействия с биржей OKX"""
    # Константы управления
    HEALTH_CHECK_INTERVAL = 120  # Интервал проверок (сек)
    RUN_DURATION = 300           # Продолжительность работы (сек)
    
    def __init__(self, config: Dict[str, str], demo: bool = True):
        # Конфигурация API
        self.api_key = config.get("api_key", "").strip()
        self.secret_key = config.get("secret_key", "").strip()
        self.passphrase = config.get("passphrase", "").strip()
        self.demo = demo
        
        # Валидация учетных данных
        if not all([self.api_key, self.secret_key, self.passphrase]):
            raise ConfigurationError("Missing API credentials")
        
        # Состояние системы
        self.logger = get_logger("OkxExchange")
        self.state = ExchangeState.DISCONNECTED
        self.balance = Decimal("0")
        self.session: Optional[ClientSession] = None
        self.stop_event = asyncio.Event()
        self.run_task: Optional[asyncio.Task] = None
        self.closing = False
        self.symbol_cache = {}  # Кеш параметров инструментов
        
        # Логирование режима работы
        if self.demo:
            self.logger.info("DEMO mode activated")
        else:
            self.logger.warning("LIVE TRADING mode activated")

    async def connect(self) -> bool:
        """Установка соединения с биржей"""
        if self.closing:
            return False
            
        self._update_state(ExchangeState.CONNECTING)
        try:
            # Закрытие старой сессии при необходимости
            if self.session and not self.session.closed:
                await self.session.close()
                
            # Создание новой сессии
            self.session = ClientSession(timeout=ClientTimeout(total=10))
            
            # Проверка баланса как тест соединения
            usdt_balance = await self.get_balance(Coin("USDT"))
            if usdt_balance is None:
                raise ExchangeError("Balance check failed")
                
            self.balance = usdt_balance
            self._update_state(ExchangeState.CONNECTED)
            return True
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            self._update_state(ExchangeState.NETWORK_ERROR)
            return False
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self._update_state(ExchangeState.API_ERROR)
            return False

    async def run(self):
        """Запуск фонового процесса мониторинга состояния"""
        if self.closing or (self.run_task and not self.run_task.done()):
            self.logger.warning("Run loop already active")
            return
            
        self.stop_event.clear()
        if not await self.connect():
            raise ExchangeError("Initial connection failed")
            
        start_time = asyncio.get_event_loop().time()
        self.logger.info("Starting health monitoring")

        async def health_loop():
            """Цикл проверки состояния биржи"""
            try:
                while not self.stop_event.is_set():
                    if self.closing:
                        break
                    await self.check_health()
                    await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
            except asyncio.CancelledError:
                self.logger.info("Monitoring cancelled")
            finally:
                if not self.closing:
                    await self.close()
                self.logger.info("Monitoring stopped")

        self.run_task = asyncio.create_task(health_loop())

    async def stop(self):
        """Остановка фонового процесса"""
        if self.closing or not self.run_task or self.run_task.done():
            return
            
        self.logger.info("Stopping health monitoring")
        self.stop_event.set()
        self.run_task.cancel()
        try:
            await self.run_task
        except asyncio.CancelledError:
            pass

    async def check_health(self):
        """Проверка текущего состояния биржи"""
        try:
            # Повторное подключение при проблемах
            if self.state in (ExchangeState.DISCONNECTED, ExchangeState.NETWORK_ERROR):
                await self.connect()
                
            # Проверка баланса
            balance = await self.get_balance(Coin("USDT"))
            if balance is None:
                self._update_state(ExchangeState.API_ERROR)
                return
                
            self.balance = balance
            self._update_state(
                ExchangeState.ACTIVE if balance >= 10 
                else ExchangeState.BALANCE_LOW
            )
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            self._update_state(ExchangeState.NETWORK_ERROR)
        except aiohttp.ClientResponseError as e:
            self._update_state(
                ExchangeState.RATE_LIMITED if e.status == 429 
                else ExchangeState.API_ERROR
            )
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            self._update_state(ExchangeState.API_ERROR)

    async def close(self):
        """Корректное завершение работы с биржей"""
        if self.closing:
            return
            
        self.closing = True
        await self.stop()
        
        if self.session and not self.session.closed:
            await self.session.close()
            self.logger.info("Session closed")
            
        self.session = None
        self._update_state(ExchangeState.DISCONNECTED)

    async def get_balance(self, coin: Coin) -> Optional[Decimal]:
        """Получение доступного баланса монеты"""
        if self.closing:
            return None
            
        data, ok = await self._request("GET", "/api/v5/account/balance")
        if not ok or not data or not isinstance(data, list):
            self.logger.error("Invalid balance response")
            return None
            
        try:
            # Поиск баланса в структуре ответа OKX
            for account in data:
                for detail in account.get("details", []):
                    if detail.get("ccy") == coin.symbol:
                        return Decimal(detail.get("availBal", "0"))
            return Decimal("0")
        except Exception as e:
            self.logger.error(f"Balance error: {e}")
            return None

    async def get_symbol_price(self, coin: Coin) -> Decimal:
        """Получение текущей цены торговой пары"""
        if self.closing:
            return Decimal("0")
            
        params = {"instId": coin.symbol_id}
        data, ok = await self._request("GET", "/api/v5/market/ticker", params)
        if not ok or not data or not isinstance(data, list):
            self.logger.error(f"Price error for {coin.symbol}")
            return Decimal("0")
            
        try:
            return Decimal(data[0].get("last", "0"))
        except Exception as e:
            self.logger.error(f"Price parsing error: {e}")
            return Decimal("0")

    async def get_symbol_details(self, coin: Coin) -> Dict[str, Any]:
        """Получение параметров торгового инструмента с кешированием"""
        if coin.symbol in self.symbol_cache:
            return self.symbol_cache[coin.symbol]
            
        params = {"instType": "SWAP", "instId": coin.symbol_id}
        data, ok = await self._request("GET", "/api/v5/public/instruments", params)
        
        # Возврат значений по умолчанию при ошибке
        if not ok or not data:
            self.logger.warning(f"Using defaults for {coin.symbol}")
            return {
                "minSz": Decimal("0.01"),
                "lotSz": Decimal("0.01"),
                "tickSz": Decimal("0.01")
            }
            
        try:
            details = {
                "minSz": Decimal(data[0].get("minSz", "0.01")),
                "lotSz": Decimal(data[0].get("lotSz", "0.01")),
                "tickSz": Decimal(data[0].get("tickSz", "0.01"))
            }
            self.symbol_cache[coin.symbol] = details
            return details
        except Exception as e:
            self.logger.error(f"Symbol details error: {e}")
            return {
                "minSz": Decimal("0.01"),
                "lotSz": Decimal("0.01"),
                "tickSz": Decimal("0.01")
            }

    async def place_limit_order(self, coin: Coin, side: str, price: Decimal, size: Decimal) -> Optional[str]:
        """Размещение лимитного ордера с коррекцией параметров"""
        if self.closing:
            return None
            
        # Получение и применение торговых параметров
        details = await self.get_symbol_details(coin)
        size = self._adjust_size(size, details)
        price = self._adjust_price(price, details)
        
        # Валидация параметров
        if size <= 0 or price <= 0:
            self.logger.error("Invalid order parameters")
            return None
            
        # Формирование запроса
        order_data = {
            "instId": coin.symbol_id,
            "tdMode": "isolated",
            "side": side.lower(),
            "ordType": "limit",
            "px": str(price),
            "sz": str(size)
        }
        
        self.logger.info(f"Placing {side} order: {coin.symbol}@{price}x{size}")
        return await self._submit_order(order_data)

    async def cancel_order(self, coin: Coin, order_id: str) -> bool:
        """Отмена конкретного ордера"""
        if self.closing:
            return False
            
        order_data = {"instId": coin.symbol_id, "ordId": order_id}
        _, ok = await self._request("POST", "/api/v5/trade/cancel-order", order_data)
        return ok

    async def cancel_all_orders(self, coin: Coin) -> List[str]:
        """Отмена всех активных ордеров для инструмента"""
        if self.closing:
            return []
            
        data, ok = await self._request("GET", "/api/v5/trade/orders-pending", {"instId": coin.symbol_id})
        if not ok or not data:
            return []
            
        # Формирование пакета для отмены
        orders_to_cancel = [
            {"instId": coin.symbol_id, "ordId": order["ordId"]}
            for order in data
        ]
        if not orders_to_cancel:
            return []
            
        cancel_data, ok = await self._request("POST", "/api/v5/trade/cancel-batch-orders", orders_to_cancel)
        if not ok:
            return []
            
        # Возврат успешно отмененных ордеров
        return [item["ordId"] for item in cancel_data if item.get("sCode") == "0"]

    async def get_open_orders(self, coin: Coin) -> Dict[str, Any]:
        """Получение активных ордеров"""
        if self.closing:
            return {}
            
        data, ok = await self._request("GET", "/api/v5/trade/orders-pending", {"instId": coin.symbol_id})
        if not ok or not data:
            return {}
            
        return {order["ordId"]: order for order in data}

    async def get_status_report(self) -> Dict[str, Any]:
        """Отчет о текущем состоянии подключения"""
        return {
            "state": self.state.name,
            "balance": str(self.balance),
            "operational": self.state in (
                ExchangeState.ACTIVE,
                ExchangeState.CONNECTED,
                ExchangeState.BALANCE_LOW
            ),
            "needs_attention": self.state in (
                ExchangeState.API_ERROR,
                ExchangeState.NETWORK_ERROR,
                ExchangeState.RATE_LIMITED
            )
        }

    async def _request(self, method: str, path: str, payload: Any = None) -> Tuple[Any, bool]:
        """Базовый метод выполнения запросов к API"""
        if self.closing or not self.session:
            return [], False
            
        # Подготовка URL и тела запроса
        url = "https://www.okx.com" + path
        now = datetime.now(timezone.utc)
        timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{now.microsecond//1000:03d}Z"
        
        # Обработка параметров для GET-запросов
        if method.upper() == "GET" and payload:
            sorted_params = sorted(payload.items())
            encoded_params = "&".join(f"{k}={v}" for k, v in sorted_params)
            full_url = f"{url}?{encoded_params}"
            body = ""
            sign_path = f"{path}?{encoded_params}"
        else:
            full_url = url
            body = json.dumps(payload, separators=(",", ":")) if payload else ""
            sign_path = path
            
        # Генерация подписи
        message = f"{timestamp}{method.upper()}{sign_path}{body}"
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()
        ).decode()

        # Заголовки запроса
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            **({"x-simulated-trading": "1"} if self.demo else {}),
        }
        
        if body:
            headers["Content-Length"] = str(len(body))

        try:
            # Выполнение запроса
            async with self.session.request(
                method, full_url, headers=headers, 
                data=body if method.upper() == "POST" else None,
                timeout=ClientTimeout(total=10)
            ) as response:
                data = await response.json()
                ok = response.status == 200 and data.get("code") == "0"
                return data.get("data", []), ok
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self.logger.error(f"Request failed: {method} {path} - {e}")
            return [], False
        except Exception as e:
            self.logger.exception(f"Unexpected error: {e}")
            return [], False

    async def _submit_order(self, order_data: dict) -> Optional[str]:
        """Отправка ордера с повторными попытками"""
        for attempt in range(3):
            try:
                data, ok = await self._request("POST", "/api/v5/trade/order", order_data)
                if ok and data and isinstance(data, list):
                    return data[0].get("ordId")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                self.logger.warning(f"Order attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2 ** attempt)
        return None

    def _adjust_size(self, size: Decimal, details: Dict[str, Decimal]) -> Decimal:
        """Коррекция размера под требования биржи"""
        min_size = details["minSz"]
        lot_size = details["lotSz"]
        adjusted = (size // lot_size) * lot_size
        return max(adjusted, min_size)

    def _adjust_price(self, price: Decimal, details: Dict[str, Decimal]) -> Decimal:
        """Коррекция цены под требования биржи"""
        tick_size = details["tickSz"]
        return (price // tick_size) * tick_size

    def _update_state(self, new_state: ExchangeState):
        """Обновление состояния системы с логированием"""
        if self.state == new_state:
            return
            
        self.logger.info(f"State changed: {self.state.name} -> {new_state.name}")
        self.state = new_state

####################
### core/bot.py
####################
"""Ядро торгового бота: исполнение стратегии"""
import asyncio
import logging
from decimal import Decimal
from typing import Dict, Optional

# Внедряем зависимость через абстракции
class TradingBot(ABC):
    @abstractmethod
    async def execute_strategy(self, signals: Dict, price: Decimal):
        pass

class Bot (TradingBot):
    """Координатор между стратегией, биржей и управлением ордерами"""
    def __init__(self, exchange: Exchange, strategy: Strategy, order_manager: OrderManager, position_manager: PositionManager):
        # Компоненты системы
        self.exchange = exchange
        self.strategy = strategy
        self.order_manager = order_manager
        self.position_manager = position_manager
        
        # Состояние бота
        self.coin = strategy.coin
        self.logger = logging.getLogger(f"Bot:{self.coin.symbol}")
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.interval = 30  # Интервал торгового цикла (сек)
        self.current_position: Optional[Position] = None  # Текущая позиция

    async def start(self):
        """Запуск торгового цикла"""
        if self.running:
            self.logger.warning("Already running")
            return
            
        self.running = True
        self.task = asyncio.create_task(self.trading_loop())
        self.logger.info("Trading started")

    async def stop(self):
        """Остановка торгов с отменой ордеров"""
        if not self.running:
            return
            
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
                
        # Отмена активных ордеров
        for order in self.order_manager.get_active_orders():
            await self.exchange.cancel_order(self.coin, order.id)
            
        self.logger.info("Trading stopped")

    async def trading_loop(self):
        """Основной цикл исполнения торговой стратегии"""
        while self.running:
            try:
                # Проверка доступности биржи
                if not await self.check_exchange_status():
                    await asyncio.sleep(10)
                    continue
                    
                # Обновление данных
                await self.update_position()
                await self.update_orders()
                price = await self.exchange.get_symbol_price(self.coin)
                
                # Генерация и исполнение сигналов
                signals = self.strategy.generate_signals(price, self.current_position)
                await self.execute_strategy(signals, price)
                
                # Логирование состояния
                self.log_status(price)
                await asyncio.sleep(self.interval)
                
            except asyncio.CancelledError:
                break
            except ExchangeError as e:
                self.logger.error(f"Exchange error: {e}")
                await asyncio.sleep(30)
            except StrategyError as e:
                self.logger.error(f"Strategy error: {e}")
                await asyncio.sleep(10)
            except Exception as e:
                self.logger.exception(f"Unexpected error: {e}")
                await asyncio.sleep(60)

    async def check_exchange_status(self) -> Tuple[bool, Dict[str, Any]]:
        """Проверка готовности биржи к торговле"""
        status = await self.exchange.get_status_report()
        if status["needs_attention"]:
            self.logger.error(f"Exchange issue: {status['state']}")
            return False, status
        else:
            self.logger.info(f"Exchange operational: {status['state']}")
            return True, status

    async def update_position(self):
        """Обновление данных о текущей позиции"""
        if self.current_position and self.current_position.status == PositionStatus.OPEN:
            # В реальной системе здесь запрос к бирже
            self.current_position.update_price(
                await self.exchange.get_symbol_price(self.coin)
            )

    async def update_orders(self):
        """Обновление статусов ордеров"""
        open_orders = await self.exchange.get_open_orders(self.coin)
        for order_id, order_data in open_orders.items():
            status = order_data.get("state")
            filled = Decimal(order_data.get("fillSz", "0"))
            
            # Обработка исполнения
            if status in ("filled", "partially_filled"):
                self.order_manager.update_order_fill(
                    order_id,
                    filled,
                    Decimal(order_data.get("avgPx", "0")),
                    Decimal(order_data.get("fee", "0")),
                    order_data.get("feeCcy", "USDT")
                )
                
                # Обновление позиции
                position = self.position_manager.get_position_for_order(order_id)
                if position:
                    position.update_price(
                        await self.exchange.get_symbol_price(self.coin)
                    )

    async def execute_strategy(self, signals: Dict, price: Decimal):
        """Исполнение торговых сигналов стратегии"""
        # Отмена устаревших ордеров
        await self.cancel_outdated_orders(signals)
        
        # Размещение новых ордеров
        await self.place_new_orders(signals, price)

    async def cancel_outdated_orders(self, signals: Dict):
        """Отмена ордеров, не соответствующих текущим сигналам"""
        for order in self.order_manager.get_active_orders():
            if self.should_cancel_order(order, signals):
                success = await self.exchange.cancel_order(self.coin, order.id)
                if success:
                    self.order_manager.close_order(order.id, "strategy_change")

    async def place_new_orders(self, signals: Dict, price: Decimal):
        """Размещение ордеров на основе сигналов"""
        risk_params = self.strategy.get_risk_parameters()
        max_orders = risk_params.get("max_orders", 5)
        order_size = risk_params.get("order_size", Decimal("0.01"))
        
        # Размещение ордеров на покупку
        for buy_price in signals.get("buy_levels", [])[:max_orders]:
            if not self.order_exists("buy", buy_price):
                await self.place_order("buy", buy_price, order_size)
        
        # Размещение ордеров на продажу
        for sell_price in signals.get("sell_levels", [])[:max_orders]:
            if not self.order_exists("sell", sell_price):
                await self.place_order("sell", sell_price, order_size)

    async def place_order(self, side: str, price: Decimal, size: Decimal):
        """Размещение ордера и обновление позиции"""
        order_id = await self.exchange.place_limit_order(self.coin, side, price, size)
        if not order_id:
            return
            
        # Создание объекта ордера
        order = self.order_manager.create_order(
            order_id, side, price, size, self.coin.symbol, 
            type(self.strategy).__name__
        )
        
        # Управление позицией
        if not self.current_position or self.current_position.status != PositionStatus.OPEN:
            # Размер отрицательный для продаж
            position_size = size if side == "buy" else -size
            self.current_position = self.position_manager.open_position(
                self.coin.symbol, 
                type(self.strategy).__name__,
                position_size,
                price
            )
            
        # Привязка ордера к позиции
        self.position_manager.add_order_to_position(
            self.current_position.id,
            order_id,
            side,
            size,
            price,
            Decimal("0")  # Комиссия будет обновлена позже
        )

    def order_exists(self, side: str, price: Decimal) -> bool:
        """Проверка наличия активного ордера по цене"""
        return any(
            o.side == side and abs(o.price - price) < Decimal("0.0001")
            for o in self.order_manager.get_active_orders()
        )

    def should_cancel_order(self, order: Any, signals: Dict) -> bool:
        """Определение необходимости отмены ордера"""
        # Устаревшие ордера на покупку
        if order.side == "buy" and order.price not in signals.get("buy_levels", []):
            return True
        # Устаревшие ордера на продажу
        if order.side == "sell" and order.price not in signals.get("sell_levels", []):
            return True
        return False

    def log_status(self, price: Decimal):
        """Логирование текущего состояния"""
        active_orders = len(self.order_manager.get_active_orders())
        pos_size = self.current_position.current_size if self.current_position else 0
        self.logger.info(
            f"Orders: {active_orders} | Position: {pos_size} | Price: {price}"
        )

    def get_performance_report(self) -> Dict[str, Any]:
        """Формирование отчета о производительности"""
        return {
            "strategy": type(self.strategy).__name__,
            "coin": self.coin.symbol,
            "orders": self.order_manager.strategy_performance(type(self.strategy).__name__),
            "positions": self.position_manager.strategy_performance(type(self.strategy).__name__),
            "current_position": self.current_position.to_dict() if self.current_position else None
        }


####################
### main.py
####################
"""Точка входа и интерактивный CLI"""
import os
import json
import asyncio
from decimal import Decimal


# Поддерживаемые монеты
COINS = {
    "USDT": Coin("USDT"),
    "BTC": Coin("BTC"),
    "ETH": Coin("ETH"),
    "SOL": Coin("SOL"),
    "XRP": Coin("XRP")
}

async def command_loop():
    """Интерактивный интерфейс управления"""
    # Загрузка конфигурации
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        return
        
    with open(config_path, "r") as f:
        config = json.load(f)
    
    # Инициализация биржи
    exchange = OkxExchange(config, demo=True)
    bots = {}  # Активные торговые боты
    
    print("OKX Trading Bot CLI. Type 'help' for commands.")
    
    while True:
        try:
            # Обработка команд пользователя
            cmd_line = await asyncio.to_thread(input, "> ")
            parts = cmd_line.strip().split()
            if not parts:
                continue
                
            cmd = parts[0].lower()
            
            if cmd == "help":
                print_help()
            elif cmd == "coins":
                print(", ".join(COINS.keys()))
            elif cmd == "start":
                await exchange.run()
                print("Exchange monitoring started")
            elif cmd == "stop":
                await exchange.stop()
                print("Exchange monitoring stopped")
            elif cmd == "balance":
                await handle_balance(exchange, parts)
            elif cmd == "price":
                await handle_price(exchange, parts)
            elif cmd == "order":
                await handle_order(exchange, parts)
            elif cmd == "cancel":
                await handle_cancel(exchange, parts)
            elif cmd == "cancel_all":
                await handle_cancel_all(exchange, parts)
            elif cmd == "status":
                await handle_status(exchange)
            elif cmd == "init_bot":
                await handle_init_bot(exchange, bots, parts)
            elif cmd == "start_bot":
                await handle_start_bot(bots, parts)
            elif cmd == "stop_bot":
                await handle_stop_bot(bots, parts)
            elif cmd == "bot_status":
                await handle_bot_status(bots, parts)
            elif cmd == "quit":
                await handle_quit(exchange, bots)
                break
            else:
                print(f"Unknown command: {cmd}")
                
        except Exception as e:
            print(f"Error: {e}")

def print_help():
    """Вывод списка команд"""
    print("""
    Available commands:
      coins             - List supported coins
      start             - Start exchange monitoring
      stop              - Stop exchange monitoring
      balance [COIN]    - Get balance (default: USDT)
      price COIN        - Get current price
      order COIN SIDE PRICE SIZE - Place limit order
      cancel COIN ORDER_ID - Cancel order
      cancel_all COIN   - Cancel all orders for coin
      status            - Exchange status report
      init_bot COIN LOWER UPPER LEVELS SIZE - Initialize grid bot
      start_bot COIN    - Start trading bot
      stop_bot COIN     - Stop trading bot
      bot_status COIN   - Bot performance report
      quit              - Exit program
    """)

async def handle_balance(exchange, parts):
    """Обработка запроса баланса"""
    symbol = parts[1].upper() if len(parts) > 1 else "USDT"
    coin = COINS.get(symbol)
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return
        
    balance = await exchange.get_balance(coin)
    if balance is None:
        print("Failed to get balance")
    else:
        print(f"{symbol} balance: {balance}")

async def handle_price(exchange, parts):
    """Обработка запроса цены"""
    if len(parts) < 2:
        print("Specify coin: price BTC")
        return
        
    symbol = parts[1].upper()
    coin = COINS.get(symbol)
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return
        
    price = await exchange.get_symbol_price(coin)
    print(f"{symbol} price: {price}")

async def handle_order(exchange, parts):
    """Обработка размещения ордера"""
    if len(parts) < 5:
        print("Usage: order COIN SIDE PRICE SIZE")
        return
        
    symbol, side, price_str, size_str = parts[1:5]
    coin = COINS.get(symbol.upper())
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return
        
    try:
        price = Decimal(price_str)
        size = Decimal(size_str)
    except:
        print("Invalid price or size")
        return
        
    order_id = await exchange.place_limit_order(coin, side, price, size)
    if order_id:
        print(f"Order placed: {order_id}")
    else:
        print("Failed to place order")

async def handle_cancel(exchange, parts):
    """Обработка отмены ордера"""
    if len(parts) < 3:
        print("Usage: cancel COIN ORDER_ID")
        return
        
    symbol, order_id = parts[1:3]
    coin = COINS.get(symbol.upper())
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return
        
    success = await exchange.cancel_order(coin, order_id)
    print("Order canceled" if success else "Failed to cancel")

async def handle_cancel_all(exchange, parts):
    """Обработка отмены всех ордеров"""
    if len(parts) < 2:
        print("Usage: cancel_all COIN")
        return
        
    symbol = parts[1].upper()
    coin = COINS.get(symbol)
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return
        
    canceled = await exchange.cancel_all_orders(coin)
    if canceled:
        print(f"Canceled orders: {', '.join(canceled)}")
    else:
        print("No orders to cancel")

async def handle_status(exchange):
    """Вывод состояния биржи"""
    status = await exchange.get_status_report()
    print(f"State: {status['state']}")
    print(f"Balance: {status['balance']} USDT")
    print(f"Operational: {'Yes' if status['operational'] else 'No'}")
    print(f"Needs attention: {'Yes' if status['needs_attention'] else 'No'}")

async def handle_init_bot(exchange, bots, parts):
    """Инициализация торгового бота"""
    if len(parts) < 6:
        print("Usage: init_bot COIN LOWER UPPER LEVELS SIZE")
        return
        
    symbol, lower_str, upper_str, levels_str, size_str = parts[1:6]
    coin = COINS.get(symbol.upper())
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return
        
    try:
        lower = Decimal(lower_str)
        upper = Decimal(upper_str)
        levels = int(levels_str)
        size = Decimal(size_str)
    except:
        print("Invalid parameters")
        return
        
    # Инициализация стратегии и менеджеров
    strategy = GridStrategy(coin, lower, upper, levels, size)
    order_manager = OrderManager()
    position_manager = PositionManager()
    
    # Создание бота
    bot = Bot(exchange, strategy, order_manager, position_manager)
    bots[symbol.upper()] = bot
    print(f"Bot initialized for {symbol}")

async def handle_start_bot(bots, parts):
    """Запуск торгового бота"""
    if len(parts) < 2:
        print("Usage: start_bot COIN")
        return
        
    symbol = parts[1].upper()
    bot = bots.get(symbol)
    if not bot:
        print(f"No bot for {symbol}")
        return
        
    await bot.start()
    print(f"Bot started for {symbol}")

async def handle_stop_bot(bots, parts):
    """Остановка торгового бота"""
    if len(parts) < 2:
        print("Usage: stop_bot COIN")
        return
        
    symbol = parts[1].upper()
    bot = bots.get(symbol)
    if not bot:
        print(f"No bot for {symbol}")
        return
        
    await bot.stop()
    print(f"Bot stopped for {symbol}")

async def handle_bot_status(bots, parts):
    """Отчет о работе бота"""
    if len(parts) < 2:
        print("Usage: bot_status COIN")
        return
        
    symbol = parts[1].upper()
    bot = bots.get(symbol)
    if not bot:
        print(f"No bot for {symbol}")
        return
        
    report = bot.get_performance_report()
    print(f"Strategy: {report['strategy']}")
    print(f"Coin: {report['coin']}")
    print(f"Orders: {report['orders']['total_orders']} | Win rate: {report['orders']['win_rate']:.2%}")
    print(f"Positions: {report['positions']['total_positions']} | Win rate: {report['positions']['win_rate']:.2%}")
    if report['current_position']:
        print(f"Current position: Size={report['current_position']['size']} | PnL={report['current_position']['realized_pnl']}")

async def handle_quit(exchange, bots):
    """Корректное завершение работы"""
    print("Stopping bots...")
    for bot in bots.values():
        await bot.stop()
    
    print("Stopping exchange...")
    await exchange.stop()
    await exchange.close()
    
    print("Goodbye!")

if __name__ == "__main__":
    asyncio.run(command_loop())