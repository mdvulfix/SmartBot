####################
### core/bot.py
####################

"""Ядро торгового бота: исполнение стратегии"""
import asyncio
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Optional, Tuple, Any

from utils.logger import get_logger
from core.exchange import Exchange
from core.exceptions import ExchangeError, StrategyError
from core.strategy import Strategy
from models.coin import Coin
from models.position import Position, PositionStatus
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager

class TradingBot(ABC):
    @abstractmethod
    async def execute_strategy(self, signals: Dict, price: Decimal):
        pass

class Bot(TradingBot):
    """Координатор между стратегией, биржей и управлением ордерами"""
    def __init__(self, exchange: Exchange, strategy: Strategy, order_manager: OrderManager, position_manager: PositionManager):
        self.exchange = exchange
        self.strategy = strategy
        self.order_manager = order_manager
        self.position_manager = position_manager

        self.coin = strategy.coin
        self.logger = get_logger(f"Bot:{self.coin.symbol}")
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.interval = 30  # Интервал торгового цикла (сек)
        self.current_position: Optional[Position] = None

    async def start(self):
        if self.running:
            self.logger.warning("Already running")
            return
        self.running = True
        self.task = asyncio.create_task(self.trading_loop())
        self.logger.info("Trading started")

    async def stop(self):
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
            try:
                await self.exchange.cancel_order(self.coin, order.id)
            except Exception:
                pass

        self.logger.info("Trading stopped")

    async def trading_loop(self):
        while self.running:
            try:
                ok, _status = await self.check_exchange_status()
                if not ok:
                    await asyncio.sleep(10)
                    continue

                await self.update_position()
                await self.update_orders()
                price = await self.exchange.get_symbol_price(self.coin)

                signals = self.strategy.generate_signals(price, self.current_position)
                await self.execute_strategy(signals, price)

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
        status = await self.exchange.get_status_report()
        if status.get("needs_attention"):
            self.logger.error(f"Exchange issue: {status['state']}")
            return False, status
        self.logger.info(f"Exchange operational: {status['state']}")
        return True, status

    async def update_position(self):
        if self.current_position and self.current_position.status == PositionStatus.OPEN:
            self.current_position.update_price(await self.exchange.get_symbol_price(self.coin))

    async def update_orders(self):
        open_orders = await self.exchange.get_open_orders(self.coin)
        for order_id, order_data in open_orders.items():
            state = str(order_data.get("state", "")).lower()
            filled = Decimal(str(order_data.get("fillSz", "0")))
            avg_px = Decimal(str(order_data.get("avgPx", "0")))
            fee = Decimal(str(order_data.get("fee", "0")))
            fee_ccy = str(order_data.get("feeCcy", "USDT"))

            if state in ("filled", "partially_filled"):
                self.order_manager.update_order_fill(order_id, filled, avg_px, fee, fee_ccy)
                position = self.position_manager.get_position_for_order(order_id)
                if position:
                    position.update_price(await self.exchange.get_symbol_price(self.coin))

    async def execute_strategy(self, signals: Dict, price: Decimal):
        await self.cancel_outdated_orders(signals)
        await self.place_new_orders(signals, price)

    async def cancel_outdated_orders(self, signals: Dict):
        buy_levels = set(signals.get("buy_levels", []))
        sell_levels = set(signals.get("sell_levels", []))

        for order in list(self.order_manager.get_active_orders()):
            should_cancel = False
            if order.side == "buy" and order.price not in buy_levels:
                should_cancel = True
            if order.side == "sell" and order.price not in sell_levels:
                should_cancel = True

            if should_cancel:
                success = await self.exchange.cancel_order(self.coin, order.id)
                if success:
                    self.order_manager.close_order(order.id, "strategy_change")

    async def place_new_orders(self, signals: Dict, price: Decimal):
        risk_params = self.strategy.get_risk_parameters()
        max_orders = int(risk_params.get("max_orders", 5))
        order_size = Decimal(str(risk_params.get("order_size", Decimal("0.01"))))

        for buy_price in signals.get("buy_levels", [])[:max_orders]:
            if not self.order_exists("buy", buy_price):
                await self.place_order("buy", buy_price, order_size)

        for sell_price in signals.get("sell_levels", [])[:max_orders]:
            if not self.order_exists("sell", sell_price):
                await self.place_order("sell", sell_price, order_size)

    async def place_order(self, side: str, price: Decimal, size: Decimal):
        order_id = await self.exchange.place_limit_order(self.coin, side, price, size)
        if not order_id:
            return

        order = self.order_manager.create_order(
            order_id, side, price, size, self.coin.symbol, type(self.strategy).__name__
        )

        if not self.current_position or self.current_position.status != PositionStatus.OPEN:
            position_size = size if side == "buy" else -size
            self.current_position = self.position_manager.open_position(
                self.coin.symbol, type(self.strategy).__name__, position_size, price
            )

        self.position_manager.add_order_to_position(
            self.current_position.id, order_id, side, size, price, Decimal("0")
        )

    def order_exists(self, side: str, price: Decimal) -> bool:
        eps = Decimal("0.00000001")
        return any(
            o.side == side and abs(o.price - price) < eps
            for o in self.order_manager.get_active_orders()
        )

    def log_status(self, price: Decimal):
        active_orders = len(self.order_manager.get_active_orders())
        pos_size = self.current_position.current_size if self.current_position else Decimal("0")
        self.logger.info(f"Orders: {active_orders} | Position: {pos_size} | Price: {price}")

    def get_performance_report(self) -> Dict[str, Any]:
        return {
            "strategy": type(self.strategy).__name__,
            "coin": self.coin.symbol,
            "orders": self.order_manager.strategy_performance(type(self.strategy).__name__),
            "positions": self.position_manager.strategy_performance(type(self.strategy).__name__),
            "current_position": self.current_position.to_dict() if self.current_position else None
        }
