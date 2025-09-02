# backtest/runner.py
from decimal import Decimal
from typing import List, Dict, Any
from models.coin import Coin
from backtest.async_exchange import AsyncBacktestExchange
from core.bot import Bot
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager

class BacktestRunner:
    """
    Асинхронный BacktestRunner, использующий асинхронную имитацию биржи и сам Bot.
    - candles: list[dict] с ключами timestamp,open,high,low,close,volume
    - coin: Coin
    - strategy: Strategy (напр. SmaStrategy)
    """
    def __init__(self, candles: List[Dict[str, Any]], coin: Coin, strategy, fee_rate: Decimal = Decimal("0.0005"), slippage: Decimal = Decimal("0.0")):
        self.candles = candles
        self.coin = coin
        self.strategy = strategy
        self.exchange = AsyncBacktestExchange(fee_rate=fee_rate, slippage=slippage)
        self.order_manager = OrderManager()
        self.position_manager = PositionManager()
        self.bot = Bot(self.exchange, self.strategy, self.order_manager, self.position_manager)
        self.trade_history = []

    async def run(self):
        # Пошаговая имитация: для каждой свечи — обновляем exchange, просим бота действовать, затем match
        for candle in self.candles:
            await self.exchange.set_candle(candle)
            # обновление статусов, как если бы бот работал в реальном времени
            await self.bot.update_orders()
            await self.bot.update_position()

            price = await self.exchange.get_symbol_price(self.coin)
            signals = self.strategy.generate_signals(price, self.bot.current_position)

            # просим бота исполнить стратегию (создание/отмена ордеров)
            await self.bot.execute_strategy(signals, price)

            # эмулируем исполнение ордеров
            fills = await self.exchange.match_orders_with_current_candle()
            for f in fills:
                ord_id = f["ordId"]
                filled_size = f["filled_size"]
                avg_px = f["fill_price"]
                fee = Decimal(str(f["fee"]))
                fee_ccy = f.get("feeCcy", "USDT")
                # обновляем менеджер ордеров
                self.order_manager.update_order_fill(ord_id, filled_size, avg_px, fee, fee_ccy)
                # связываем ордер с позицией (как в Bot)
                pos = self.position_manager.get_position_for_order(ord_id)
                if not pos:
                    order_obj = self.order_manager.get_order(ord_id)
                    if order_obj:
                        direction_size = order_obj.size if order_obj.side == "buy" else -order_obj.size
                        new_pos = self.position_manager.open_position(self.coin.symbol, type(self.strategy).__name__, direction_size, avg_px)
                        self.position_manager.add_order_to_position(new_pos.id, ord_id, order_obj.side, order_obj.size, avg_px, fee)
                        pos = new_pos
                else:
                    order_obj = self.order_manager.get_order(ord_id)
                    if order_obj:
                        self.position_manager.add_order_to_position(pos.id, ord_id, order_obj.side, order_obj.size, avg_px, fee)

                # логируем fill
                self.trade_history.append({
                    "timestamp": f.get("timestamp"),
                    "ordId": ord_id,
                    "price": str(avg_px),
                    "size": str(filled_size),
                    "fee": str(fee)
                })

            # даём стратегии знать о закрытии бара (если реализовано)
            if hasattr(self.strategy, "on_bar"):
                self.strategy.on_bar(candle)

        return {
            "trades": len(self.trade_history),
            "trade_history": self.trade_history,
            "positions": {pid: p.to_dict() for pid, p in self.position_manager.positions.items()}
        }
