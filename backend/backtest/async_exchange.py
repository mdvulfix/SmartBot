# backtest/async_exchange.py
import asyncio
from decimal import Decimal
from typing import Dict, Any, Optional, List
from datetime import datetime
from models.coin import Coin

class AsyncBacktestExchange:
    """
    Асинхронная имитация биржи, совместимая с интерфейсом OkxExchange.
    Поддерживает: set_candle, get_balance, get_symbol_price, place_limit_order,
    cancel_order, get_open_orders, match_orders_with_current_candle.
    """
    def __init__(self, fee_rate: Decimal = Decimal("0.0005"), slippage: Decimal = Decimal("0.0")):
        self.fee_rate = fee_rate
        self.slippage = slippage
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._next_id = 1
        self.current_candle: Optional[Dict[str, Any]] = None
        self._last_price: Decimal = Decimal("0")

    async def set_candle(self, candle: Dict[str, Any]):
        self.current_candle = candle
        self._last_price = candle["close"]
        await asyncio.sleep(0)

    async def get_balance(self, coin: Coin) -> Optional[Decimal]:
        return Decimal("100000")

    async def get_symbol_price(self, coin: Coin) -> Decimal:
        return self._last_price

    async def place_limit_order(self, coin: Coin, side: str, price: Decimal, size: Decimal) -> Optional[str]:
        ordId = f"bt-{self._next_id}"
        self._next_id += 1
        self._orders[ordId] = {
            "ordId": ordId,
            "instId": coin.symbol_id,
            "side": side.lower(),
            "price": price,
            "size": size,
            "fillSz": Decimal("0"),
            "state": "open",
            "created_at": datetime.utcnow().isoformat()
        }
        await asyncio.sleep(0)
        return ordId

    async def cancel_order(self, coin: Coin, order_id: str) -> bool:
        o = self._orders.get(order_id)
        if not o or o.get("state") != "open":
            return False
        o["state"] = "canceled"
        await asyncio.sleep(0)
        return True

    async def get_open_orders(self, coin: Coin):
        await asyncio.sleep(0)
        return {oid: o for oid, o in self._orders.items() if o["state"] == "open" and o["instId"] == coin.symbol_id}

    async def get_status_report(self):
        return {"state": "BACKTEST", "balance": "100000", "operational": True, "needs_attention": False}

    async def match_orders_with_current_candle(self) -> List[Dict[str, Any]]:
        fills = []
        if not self.current_candle:
            return fills
        low = self.current_candle["low"]
        high = self.current_candle["high"]
        ts = self.current_candle.get("timestamp")
        for oid, o in list(self._orders.items()):
            if o["state"] != "open":
                continue
            price = o["price"]
            if low <= price <= high:
                filled = o["size"] - (o.get("fillSz") or Decimal("0"))
                if filled <= 0:
                    continue
                side = o["side"]
                fill_price = price * (Decimal("1") + (self.slippage if side == "sell" else -self.slippage))
                fee = abs(fill_price * filled) * self.fee_rate
                o["fillSz"] = (o.get("fillSz", Decimal("0")) or Decimal("0")) + filled
                o["state"] = "filled"
                fills.append({
                    "ordId": oid,
                    "filled_size": filled,
                    "fill_price": fill_price,
                    "fee": fee,
                    "feeCcy": "USDT",
                    "state": "filled",
                    "timestamp": ts
                })
        await asyncio.sleep(0)
        return fills
