# backtest/exchange.py
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime

from models.coin import Coin
from execution.order_manager import OrderManager
from core.exceptions import ExchangeError

class BacktestExchange:
    """
    Простейшая имитация биржи для бэктеста.
    Не async — синхронная, управляется движком.
    """
    def __init__(self, fee_rate: Decimal = Decimal("0.0005"), slippage: Decimal = Decimal("0.0000")):
        # fee_rate: комиссия от объёма (например 0.0005 = 0.05%)
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.time: Optional[datetime] = None

        # active limit orders: ordId -> order_data
        self.orders: Dict[str, Dict[str, Any]] = {}
        self._next_id = 1

    def set_time(self, ts):
        self.time = ts

    def _make_order_id(self) -> str:
        oid = f"bt-{self._next_id}"
        self._next_id += 1
        return oid

    def place_limit_order(self, coin: Coin, side: str, price: Decimal, size: Decimal) -> str:
        """
        Регистрируем лимитный ордер в стакане (ожидает исполнения при пересечении свечи).
        Возвращаем ordId.
        """
        ordId = self._make_order_id()
        self.orders[ordId] = {
            "ordId": ordId,
            "instId": coin.symbol_id,
            "side": side.lower(),
            "price": price,
            "size": size,
            "filled": Decimal("0"),
            "state": "open",
            "created_at": self.time
        }
        return ordId

    def cancel_order(self, coin: Coin, order_id: str) -> bool:
        if order_id in self.orders and self.orders[order_id]["state"] == "open":
            self.orders[order_id]["state"] = "canceled"
            return True
        return False

    def get_open_orders(self, coin: Coin) -> Dict[str, Any]:
        return {oid: o for oid, o in self.orders.items() if o["state"] == "open" and o["instId"] == coin.symbol_id}

    def match_orders_with_candle(self, candle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Проверяем все открытые ордера и заполняем их, если свеча пересекает цену.
        candle: dict with 'open','high','low','close' (Decimals) and 'timestamp'
        Возвращает список fills: {ordId, filled_size, fill_price, fee}
        """
        fills = []
        low: Decimal = candle["low"]
        high: Decimal = candle["high"]
        for ordId, o in list(self.orders.items()):
            if o["state"] != "open":
                continue
            price = o["price"]
            side = o["side"]
            size = o["size"] - o["filled"]
            if size <= 0:
                continue

            # Правило заполнения лимитного ордера:
            # для buy: если low <= price <= high (т.е. цена опустилась до уровня)
            # для sell: если low <= price <= high (т.е. цена поднялась до уровня)
            if low <= price <= high:
                # учитываем проскальзывание (здесь упрощённо)
                fill_price = price * (Decimal("1") + (self.slippage if side == "sell" else -self.slippage))
                fee = abs(fill_price * size) * self.fee_rate
                o["filled"] += size
                o["state"] = "filled"
                fills.append({
                    "ordId": ordId,
                    "filled_size": size,
                    "fill_price": fill_price,
                    "fee": fee,
                    "feeCcy": "USDT",
                    "timestamp": candle["timestamp"]
                })
        return fills
