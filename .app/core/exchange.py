"""Интерфейс взаимодействия с биржей OKX (демо)"""
import hmac
import hashlib
import base64
import json
import asyncio
import aiohttp
from aiohttp import ClientSession, ClientTimeout, ContentTypeError
from enum import Enum, auto
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict, Tuple

from models.coin import Coin
from core.exceptions import ConfigurationError, ExchangeError

from logger import get_logger


class ExchangeState(Enum):
    """Состояния подключения к бирже"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ACTIVE = auto()
    RATE_LIMITED = auto()
    BALANCE_LOW = auto()
    API_ERROR = auto()
    NETWORK_ERROR = auto()

class Exchange(ABC):
    """Абстрактный интерфейс для работы с биржей"""
    @abstractmethod
    async def connect(self) -> bool: ...

    @abstractmethod
    async def get_balance(self, coin: Coin) -> Optional[Decimal]: ...

    @abstractmethod
    async def get_symbol_price(self, coin: Coin) -> Decimal: ...

    @abstractmethod
    async def place_limit_order(self, coin: Coin, side: str, price: Decimal, size: Decimal) -> Optional[str]: ...

    @abstractmethod
    async def get_open_orders(self, coin: Coin) -> Dict[str, Any]: ...

    @abstractmethod
    async def cancel_order(self, coin: Coin, order_id: str) -> bool: ...

    @abstractmethod
    async def get_status_report(self) -> Dict[str, Any]: ...

class OkxExchange(Exchange):
    """Реализация взаимодействия с биржей OKX"""
    HEALTH_CHECK_INTERVAL = 120  # сек
    RUN_DURATION = 300

    def __init__(self, config: Dict[str, str], demo: bool = True):
        self.api_key = config.get("api_key", "").strip()
        self.secret_key = config.get("secret_key", "").strip()
        self.passphrase = config.get("passphrase", "").strip()
        self.demo = demo

        if not all([self.api_key, self.secret_key, self.passphrase]):
            raise ConfigurationError("Missing API credentials")

        self.logger = get_logger("OkxExchange")
        self.state = ExchangeState.DISCONNECTED
        self.balance = Decimal("0")
        self.session: Optional[ClientSession] = None
        self.stop_event = asyncio.Event()
        self.run_task: Optional[asyncio.Task] = None
        self.closing = False
        self.symbol_cache: Dict[str, Dict[str, Decimal]] = {}

        if self.demo:
            self.logger.info("DEMO mode activated")
        else:
            self.logger.warning("LIVE TRADING mode activated")

    # ---------- Public API ----------
    async def connect(self) -> bool:
        if self.closing:
            return False

        self._update_state(ExchangeState.CONNECTING)
        try:
            if self.session and not self.session.closed:
                await self.session.close()

            self.session = ClientSession(timeout=ClientTimeout(total=15))
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

        self.logger.info("Starting health monitoring")

        async def health_loop():
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
            if self.state in (ExchangeState.DISCONNECTED, ExchangeState.NETWORK_ERROR):
                await self.connect()

            balance = await self.get_balance(Coin("USDT"))
            if balance is None:
                self._update_state(ExchangeState.API_ERROR)
                return

            self.balance = balance
            self._update_state(ExchangeState.ACTIVE if balance >= 10 else ExchangeState.BALANCE_LOW)
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
            self._update_state(ExchangeState.NETWORK_ERROR)
        except aiohttp.ClientResponseError as e:
            self._update_state(ExchangeState.RATE_LIMITED if e.status == 429 else ExchangeState.API_ERROR)
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            self._update_state(ExchangeState.API_ERROR)

    async def close(self):
        """Корректное завершение работы с биржей"""
        if self.closing:
            return

        self.closing = True
        if self.run_task and not self.run_task.done():
            await self.stop()

        if self.session and not self.session.closed:
            await self.session.close()
            self.logger.info("Session closed")

        self.session = None
        self._update_state(ExchangeState.DISCONNECTED)

    async def get_balance(self, coin: Coin) -> Optional[Decimal]:
        if self.closing:
            return None

        data, ok = await self._request("GET", "/api/v5/account/balance")
        if not ok or not isinstance(data, list):
            self.logger.error("Invalid balance response")
            return None

        try:
            for account in data:
                for detail in account.get("details", []):
                    if detail.get("ccy") == coin.symbol:
                        return self._safe_decimal(detail.get("availBal", "0"))
            return Decimal("0")
        except Exception as e:
            self.logger.error(f"Balance error: {e}")
            return None

    async def get_symbol_price(self, coin: Coin) -> Decimal:
        if self.closing:
            return Decimal("0")

        params = {"instId": coin.symbol_id}
        data, ok = await self._request("GET", "/api/v5/market/ticker", params)
        if not ok or not isinstance(data, list) or not data:
            self.logger.error(f"Price error for {coin.symbol}")
            return Decimal("0")

        try:
            return self._safe_decimal(data[0].get("last", "0"))
        except Exception as e:
            self.logger.error(f"Price parsing error: {e}")
            return Decimal("0")

    async def get_symbol_details(self, coin: Coin) -> Dict[str, Decimal]:
        if coin.symbol in self.symbol_cache:
            return self.symbol_cache[coin.symbol]

        params = {"instType": "SWAP", "instId": coin.symbol_id}
        data, ok = await self._request("GET", "/api/v5/public/instruments", params)

        if not ok or not data:
            self.logger.warning(f"Using defaults for {coin.symbol}")
            return {"minSz": Decimal("0.01"), "lotSz": Decimal("0.01"), "tickSz": Decimal("0.01")}

        try:
            details = {
                "minSz": self._safe_decimal(data[0].get("minSz", "0.01"), "0.01"),
                "lotSz": self._safe_decimal(data[0].get("lotSz", "0.01"), "0.01"),
                "tickSz": self._safe_decimal(data[0].get("tickSz", "0.01"), "0.01"),
            }
            self.symbol_cache[coin.symbol] = details
            return details
        except Exception as e:
            self.logger.error(f"Symbol details error: {e}")
            return {"minSz": Decimal("0.01"), "lotSz": Decimal("0.01"), "tickSz": Decimal("0.01")}

    async def place_limit_order(self, coin: Coin, side: str, price: Decimal, size: Decimal) -> Optional[str]:
        if self.closing:
            return None

        details = await self.get_symbol_details(coin)
        size = self._adjust_size(size, details)
        price = self._adjust_price(price, details)

        if size <= 0 or price <= 0:
            self.logger.error("Invalid order parameters")
            return None

        order_data = {
            "instId": coin.symbol_id,
            "tdMode": "isolated",
            "side": side.lower(),
            "ordType": "limit",
            "px": str(price),
            "sz": str(size)
        }

        self.logger.info(f"Placing {side.upper()} order: {coin.symbol}@{price} x {size}")
        return await self._submit_order(order_data)

    async def cancel_order(self, coin: Coin, order_id: str) -> bool:
        if self.closing:
            return False

        order_data = {"instId": coin.symbol_id, "ordId": order_id}
        _, ok = await self._request("POST", "/api/v5/trade/cancel-order", order_data)
        return ok

    async def cancel_all_orders(self, coin: Coin) -> List[str]:
        if self.closing:
            return []

        data, ok = await self._request("GET", "/api/v5/trade/orders-pending", {"instId": coin.symbol_id})
        if not ok or not data:
            return []

        orders_to_cancel = [{"instId": coin.symbol_id, "ordId": order["ordId"]} for order in data]
        if not orders_to_cancel:
            return []

        cancel_data, ok = await self._request("POST", "/api/v5/trade/cancel-batch-orders", orders_to_cancel)
        if not ok:
            return []

        return [item["ordId"] for item in cancel_data if item.get("sCode") == "0"]

    async def get_open_orders(self, coin: Coin) -> Dict[str, Any]:
        if self.closing:
            return {}

        data, ok = await self._request("GET", "/api/v5/trade/orders-pending", {"instId": coin.symbol_id})
        if not ok or not data:
            return {}

        # возвращаем словарь по ordId
        result: Dict[str, Any] = {}
        for order in data:
            oid = order.get("ordId")
            if oid:
                result[oid] = order
        return result

    async def get_status_report(self) -> Dict[str, Any]:
        return {
            "state": self.state.name,
            "balance": str(self.balance),
            "operational": self.state in (ExchangeState.ACTIVE, ExchangeState.CONNECTED, ExchangeState.BALANCE_LOW),
            "needs_attention": self.state in (ExchangeState.API_ERROR, ExchangeState.NETWORK_ERROR, ExchangeState.RATE_LIMITED)
        }

    # ---------- Low-level ----------
    async def _request(self, method: str, path: str, payload: Any = None) -> Tuple[Any, bool]:
        """Базовый метод выполнения запросов к API OKX с подписью."""
        if self.closing or not self.session:
            return [], False

        url = "https://www.okx.com" + path
        now = datetime.now(timezone.utc)
        timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{now.microsecond//1000:03d}Z"

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

        message = f"{timestamp}{method.upper()}{sign_path}{body}"
        signature = base64.b64encode(
            hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256).digest()
        ).decode()

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
            async with self.session.request(
                method, full_url, headers=headers,
                data=body if method.upper() == "POST" else None,
                timeout=ClientTimeout(total=15)
            ) as response:
                try:
                    data = await response.json()
                except ContentTypeError:
                    text = await response.text()
                    self.logger.error(f"Non-JSON response: {response.status} - {text[:200]}")
                    return [], False

                ok = response.status == 200 and str(data.get("code")) == "0"
                return data.get("data", []), ok

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            self.logger.error(f"Request failed: {method} {path} - {e}")
            return [], False
        except Exception as e:
            self.logger.exception(f"Unexpected error: {e}")
            return [], False

    async def _submit_order(self, order_data: dict) -> Optional[str]:
        """Отправка ордера с повторными попытками (экспоненциальный backoff)."""
        for attempt in range(3):
            data, ok = await self._request("POST", "/api/v5/trade/order", order_data)
            if ok and data and isinstance(data, list):
                return data[0].get("ordId")
            await asyncio.sleep(2 ** attempt)
        return None
    @staticmethod
    def _safe_decimal(val: Any, default: str = "0") -> Decimal:
        try:
            if val is None:
                return Decimal(default)
            return Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal(default)
    @staticmethod
    def _adjust_size(size: Decimal, details: Dict[str, Decimal]) -> Decimal:
        """Корректное округление размера по lotSz c округлением вниз и минимумом minSz."""
        lot_size = details["lotSz"]
        min_size = details["minSz"]
        if size <= 0 or lot_size <= 0:
            return Decimal("0")
        multiplier = (size / lot_size).to_integral_value(rounding=ROUND_DOWN)
        adjusted = (multiplier * lot_size).normalize()
        return adjusted if adjusted >= min_size else min_size
    @staticmethod
    def _adjust_price(price: Decimal, details: Dict[str, Decimal]) -> Decimal:
        """Корректное округление цены по tickSz с округлением вниз."""
        tick_size = details["tickSz"]
        if price <= 0 or tick_size <= 0:
            return Decimal("0")
        multiplier = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
        return (multiplier * tick_size).normalize()

    def _update_state(self, new_state: ExchangeState):
        if self.state == new_state:
            return
        self.logger.info(f"State changed: {self.state.name} -> {new_state.name}")
        self.state = new_state
