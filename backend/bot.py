# === file: bot.py ===

import asyncio
import random
from typing import Any, Dict, Optional
from decimal import Decimal
from utils import Utils
from exchange import Exchange
from strategy import Strategy
from order import Order, OrderManager
from position import Position, PositionManager

class SmartBot:
    
    def __init__(self, exchange: Exchange, strategy: Strategy):
                
        HEALTH_CHECK_INTERVAL: int = 30
        
        self._exchange = exchange
        self._strategy = strategy
        self._coin = strategy.coin
        
        self._logger = Utils.get_logger("SmartBot")
        self._logger.info(f"SmartBot initialized for {self._coin.symbol_id}")
        
        # Менеджеры состояний
        self._order_manager = OrderManager()
        self._position_manager = PositionManager()
        
        # Текущая позиция
        self._current_position: Optional[Position] = None

        # Состояние бота
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Проверка состояния биржи
        self._helth_check_interval = 30

    async def start(self):
        if self._running:
            self._logger.warning("Bot is already running")
            return
            
        self._running = True
        self._task = asyncio.create_task(self._trading_loop())
        self._logger.info("SmartBot started")

    async def stop(self):
        """Остановка торгового бота"""
        if not self.running:
            return
            
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
                
        # Отмена всех активных ордеров при остановке
        for order in self.order_manager.get_active_orders():
            await self.exchange.cancel_order(self.coin, order.id)
            self.order_manager.close_order(
                order_id=order.id,
                reason="bot_stopped"
            )
        
        self.logger.info("SmartBot stopped")

    async def get_status(self) -> Dict[str, any]:
        """Возвращает текущее состояние бота"""
        return {
            'running': self._running,
            'active_orders': len(self._active_orders),
            'position': str(self._position),
            'coin': self._coin.symbol_id,
            'strategy': type(self._strategy).__name__
        }

    def get_position_report(self) -> Dict[str, Any]:
        """Отчет по текущей позиции"""
        if not self.current_position:
            return {"status": "no_open_position"}
        
        report = self.current_position.to_dict()
        report['orders'] = [self.order_manager.get_order(oid).to_dict() for oid in self.current_position.orders]
        return report

    def get_strategy_performance(self) -> Dict[str, Any]:
        """Расширенный отчет по производительности стратегии"""
        strategy_name = type(self.strategy).__name__
        
        return {
            "strategy": strategy_name,
            "coin": self.coin.symbol_id,
            "order_performance": self.order_manager.calculate_strategy_performance(strategy_name),
            "position_performance": self.position_manager.calculate_strategy_performance(strategy_name),
            "current_position": self.get_position_report() if self.current_position else None
        }

    async def _trading_loop(self):

        while self._running:
            try:
                # Проверка состояния биржи
                if not await self._check_exchange_health():
                    await asyncio.sleep(10)
                    continue
                
                # Обновление позиции
                await self._update_position()
                
                # Обновление активных ордеров
                await self._update_active_orders()
                
                # Получение текущей цены
                price = await self._exchange.get_symbol_price(self._coin)
                
                # Генерация торговых сигналов
                signals = self._strategy.generate_signals(price, self._position)
                
                # Управление ордерами на основе сигналов
                await self._manage_orders(signals)
                
                # Статус бота
                self._logger.info(f"Active orders: {len(self._active_orders)} | " f"Position: {self._position} | " f"Price: {price}")
                
                # Интервал между проверками
                await asyncio.sleep(self._helth_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Trading loop error: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _check_exchange_health(self) -> bool:
        status = await self._exchange.get_status_report()
        
        if status['needs_attention']:
            self._logger.error(f"Exchange issue: {status['state']}")
            return False
            
        if not status['is_operational']:
            self._logger.warning(f"Exchange not operational: {status['state']}")
            return False
            
        return True

    async def _update_position(self):
        """Обновляет информацию о позиции"""
        # Получаем текущий баланс по монете
        balance = await self.exchange.get_balance(self.coin)
        
        # Если позиция существует и размер изменился
        if self.current_position and self.current_position.status == PositionStatus.OPEN:
            if abs(self.current_position.current_size - balance) > Decimal('0.0001'):
                # Позиция изменилась - обновляем
                self.current_position.current_size = balance
                self.current_position.update_price(await self.exchange.get_symbol_price(self.coin))

    async def _update_active_orders(self):
        """Обновление информации об активных ордерах и позициях"""
        # Здесь будет запрос к бирже для получения обновлений по ордерам
        for order in self.order_manager.get_active_orders():
            # Эмуляция: 50% шанс, что ордер исполнился
            if random.random() > 0.5:
                filled_size = order.size
                filled_price = order.price
                fee = order.size * order.price * Decimal('0.0002')
                
                # Обновляем ордер
                self.order_manager.update_order_fill(
                    order_id=order.id,
                    filled_size=filled_size,
                    filled_price=filled_price,
                    fee=fee,
                    fee_currency="USDT"
                )
                
                # Обновляем позицию
                position = self.position_manager.get_position_for_order(order.id)
                if position:
                    position.update_price(await self.exchange.get_symbol_price(self.coin))
                    
                    # Если позиция закрыта
                    if position.status == PositionStatus.CLOSED:
                        self.current_position = None

    async def _manage_orders(self, signals: Dict[str, Any]):
        """Управление ордерами на основе торговых сигналов"""
        # Отмена устаревших ордеров
        await self._cancel_outdated_orders(signals)
        
        # Размещение новых ордеров
        await self._place_new_orders(signals)

    async def _cancel_outdated_orders(self, signals: Dict[str, Any]):
        """Отмена ордеров, не соответствующих текущим сигналам"""
        for order in self.order_manager.get_active_orders():
            if self._should_cancel_order(order, signals):
                success = await self.exchange.cancel_order(self.coin, order.id)
                if success:
                    self.order_manager.close_order(
                        order_id=order.id,
                        reason="outdated_signal"
                    )

    async def _place_new_orders(self, signals: Dict[str, Any]):
        """Размещение новых ордеров на основе сигналов"""
        risk_params = self._strategy.get_risk_parameters()
        max_orders = risk_params['max_orders']
        order_size = risk_params['order_size']
        
        # Размещаем ордера на покупку
        for price in signals['buy_levels']:
            if len(self._active_orders) >= max_orders:
                break
                
            if self._order_exists('buy', price):
                continue
                
            await self._place_order('buy', price, order_size)

        # Размещаем ордера на продажу
        for price in signals['sell_levels']:
            if len(self._active_orders) >= max_orders:
                break
                
            if self._order_exists('sell', price):
                continue
                
            await self._place_order('sell', price, order_size)

    async def _place_order(self, side: str, price: Decimal, size: Decimal):
        """Размещение ордера и обновление позиции"""
        try:
            order_id = await self.exchange.place_limit_order_by_size(
                coin=self.coin,
                side=side,
                price=price,
                size=size,
                trade_mode="isolated"
            )
            
            if order_id:
                # Создаем объект ордера
                order = Order(
                    order_id=order_id,
                    side=side,
                    price=price,
                    size=size,
                    coin=self.coin.symbol_id,
                    strategy=type(self.strategy).__name__
                )
                
                # Добавляем в менеджер ордеров
                self.order_manager.add_order(order)
                
                # Связываем с позицией
                if not self.current_position or self.current_position.status != PositionStatus.OPEN:
                    self.current_position = self.position_manager.open_position(
                        coin=self.coin.symbol_id,
                        strategy=type(self.strategy).__name__,
                        size=size if side == 'buy' else -size,
                        price=price
                    )
                
                # Добавляем комиссию (эмуляция, в реальности получаем с биржи)
                fee = size * price * Decimal('0.0002')  # 0.02% комиссия
                
                # Добавляем ордер к позиции
                self.position_manager.add_order_to_position(
                    position_id=self.current_position.id,
                    order_id=order_id,
                    side=side,
                    size=size,
                    price=price,
                    fee=fee
                )
                
                self.logger.info(f"Placed {side} order at {price}: {order_id}")
                return order_id
            else:
                self.logger.warning(f"Failed to place {side} order at {price}")
        except Exception as e:
            self.logger.error(f"Error placing {side} order: {e}")
        return None


    def _order_exists(self, side: str, price: Decimal) -> bool:
        return any(o['side'] == side and abs(o['price'] - price) < Decimal('0.00000001') for o in self._active_orders.values())
    
    def _should_cancel_order(self, order: Order, signals: Dict) -> bool:
        """Определяет, нужно ли отменить ордер"""
        # Логика определения устаревших ордеров
        if order.side == 'buy' and order.price not in signals['buy_levels']:
            return True
        if order.side == 'sell' and order.price not in signals['sell_levels']:
            return True
        return False