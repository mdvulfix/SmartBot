# backtest/engine.py
import csv
from decimal import Decimal, getcontext
from typing import List, Dict, Any
from datetime import datetime
from models.coin import Coin
from backtest.exchange import BacktestExchange
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager

getcontext().prec = 28

class BacktestEngine:
    """
    Engine: загружает CSV свечей, по каждой свече вызывает стратегию и эмулирует исполнение.
    """
    def __init__(self, coin: Coin, strategy, fee_rate: Decimal = Decimal("0.0005"), slippage: Decimal = Decimal("0.0")):
        self.coin = coin
        self.strategy = strategy
        self.exchange = BacktestExchange(fee_rate=fee_rate, slippage=slippage)
        self.order_manager = OrderManager()
        self.position_manager = PositionManager()

        # bookkeeping
        self.equity = Decimal("0")
        self.start_balance = Decimal("10000")  # условный стартовый USDT
        self.balance = self.start_balance
        self.trade_history: List[Dict[str, Any]] = []
        self.candles: List[Dict[str, Any]] = []

    def load_csv(self, path: str, timestamp_col: str = "timestamp"):
        with open(path, "r", newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Попытка парсинга timestamp (ISO или unix)
                ts = row.get(timestamp_col)
                try:
                    if ts.isdigit():
                        ts_val = datetime.fromtimestamp(int(ts))
                    else:
                        ts_val = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts_val = datetime.utcnow()

                candle = {
                    "timestamp": ts_val,
                    "open": Decimal(str(row["open"])),
                    "high": Decimal(str(row["high"])),
                    "low": Decimal(str(row["low"])),
                    "close": Decimal(str(row["close"])),
                    "volume": Decimal(str(row.get("volume", "0")))
                }
                self.candles.append(candle)

    def run(self):
        # инициализация стратегии (если нужно)
        if hasattr(self.strategy, "on_start"):
            self.strategy.on_start()

        for candle in self.candles:
            self.exchange.set_time(candle["timestamp"])
            # дать стратегии знать текущую цену/состояние
            price = candle["close"]
            signals = self.strategy.generate_signals(price, None)

            # Размещение ордеров по сигналам
            # ожидаем, что signals содержит 'buy_levels' и 'sell_levels' (список Decimal)
            for bp in signals.get("buy_levels", []):
                # пример: размещаем один ордер на order_size
                order_size = self.strategy.get_risk_parameters().get("order_size", Decimal("0.01"))
                ordId = self.exchange.place_limit_order(self.coin, "buy", bp, order_size)
                self.order_manager.create_order(ordId, "buy", bp, order_size, self.coin.symbol, type(self.strategy).__name__)

            for sp in signals.get("sell_levels", []):
                order_size = self.strategy.get_risk_parameters().get("order_size", Decimal("0.01"))
                ordId = self.exchange.place_limit_order(self.coin, "sell", sp, order_size)
                self.order_manager.create_order(ordId, "sell", sp, order_size, self.coin.symbol, type(self.strategy).__name__)

            # Попытка матчить ордера с этой свечой
            fills = self.exchange.match_orders_with_candle(candle)
            for f in fills:
                # обновим order_manager
                self.order_manager.update_order_fill(f["ordId"], f["filled_size"], f["fill_price"], f["fee"], f["feeCcy"])
                # привязать к позиции
                pos = self.position_manager.get_position_for_order(f["ordId"])
                if not pos:
                    # создаём новую позицию, direction implied by order side
                    order = self.order_manager.get_order(f["ordId"])
                    if order:
                        size = order.size if order.side == "buy" else -order.size
                        pos = self.position_manager.open_position(self.coin.symbol, type(self.strategy).__name__, size, f["fill_price"])
                        self.position_manager.add_order_to_position(pos.id, f["ordId"], order.side, order.size, f["fill_price"], f["fee"])
                else:
                    # если позиция уже есть, пишем в неё
                    order = self.order_manager.get_order(f["ordId"])
                    self.position_manager.add_order_to_position(pos.id, f["ordId"], order.side, order.size, f["fill_price"], f["fee"])

                # запись в trade_history при полном закрытии позиции
                if pos and pos.status == getattr(self.position_manager.get_position(pos.id), "status"):
                    # упрощённо: логируем fill
                    self.trade_history.append({
                        "timestamp": f["timestamp"],
                        "ordId": f["ordId"],
                        "price": str(f["fill_price"]),
                        "size": str(f["filled_size"]),
                        "fee": str(f["fee"])
                    })

            # Optionally let strategy update internal state on bar close
            if hasattr(self.strategy, "on_bar"):
                self.strategy.on_bar(candle)

        # Завершение
        if hasattr(self.strategy, "on_finish"):
            self.strategy.on_finish()

    def compute_report(self) -> Dict[str, Any]:
        # простая агрегация PnL по закрытым позициям
        total_realized = Decimal("0")
        for pos in self.position_manager.positions.values():
            total_realized += pos.realized_pnl

        metrics = {
            "start_balance": str(self.start_balance),
            "end_balance": str(self.start_balance + total_realized),
            "realized_pnl": str(total_realized),
            "trades": len(self.trade_history)
        }
        # max drawdown, win rate и пр. можно добавить по истории equity (упрощённо пропущено)
        return metrics
