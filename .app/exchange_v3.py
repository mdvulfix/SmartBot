# === file: exchange.py ===

import contextlib
import os
import time
import hmac
import hashlib
import base64
import json
import asyncio
import aiohttp

from enum import Enum, auto
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import datetime
from typing import Any, Tuple, Optional, List, Dict

from aiohttp import ClientSession as Session
from aiohttp import ClientTimeout as Timeout

from utils import Utils


class Exchange(ABC):
    @abstractmethod
    async def request(self, method: str, path: str, payload: Any = None) -> Tuple[Any, bool]:
        pass

    @abstractmethod
    async def get_balance(self, ccy: str = "USDT") -> Optional[Decimal]:
        pass

    @abstractmethod
    async def get_symbol_price(self, symbol: str) -> Decimal:
        pass

    @abstractmethod
    async def place_order(
        self, symbol: str, side: str, price: Decimal, size: Decimal,
        trade_mode: str = "isolated", position_side: str = "long"
    ) -> Optional[str]:
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        pass

    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> List[str]:
        pass

    @abstractmethod
    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()


class ExchangeState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ACTIVE = auto()
    RATE_LIMITED = auto()
    BALANCE_LOW = auto()
    MAINTENANCE = auto()
    API_ERROR = auto()
    NETWORK_ERROR = auto()
    ORDER_ERROR = auto()
    UNKNOWN = auto()


class OkxExchange(Exchange):
    def __init__(self):
        self._logger = Utils.get_logger("okx_exchange")

        # Load config
        config_path = os.path.join(os.path.dirname(__file__), "okx_config.json")
        if not os.path.exists(config_path):
            self._logger.error(f"Missing config file: {config_path}")
            raise FileNotFoundError(f"Missing config file: {config_path}")

        with open(config_path, "r") as f:
            cfg = json.load(f)

        self._api_key = cfg.get("api_key")
        self._secret_key = cfg.get("secret_key")
        self._passphrase = cfg.get("passphrase")
        if not all([self._api_key, self._secret_key, self._passphrase]):
            self._logger.error("Incomplete API credentials in config file")
            raise ValueError("Missing API credentials in okx_config.json")

        # Symbols to monitor
        self._symbols: List[str] = cfg.get("symbols", [])

        # HTTP session
        self._mode = cfg.get("demo", True)
        self._base_url = "https://www.okx.com"
        self._session = Session(timeout=Timeout(total=10))

        # State machine
        self._state = ExchangeState.DISCONNECTED
        self._state_history: List[Dict[str, Any]] = []
        self._last_update: Optional[datetime] = None
        self._critical_states = {
            ExchangeState.API_ERROR,
            ExchangeState.NETWORK_ERROR,
            ExchangeState.ORDER_ERROR,
            ExchangeState.MAINTENANCE
        }

        # Precision cache
        self._symbol_precision_cache: Dict[str, Tuple[int, int]] = {}

        # Run/stop control
        self._running = False
        self._run_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

        # Log demo/live mode
        if self._mode:
            self._logger.info("Running in DEMO mode")
        else:
            self._logger.warning("Running in LIVE TRADING mode")

        self._notifier = None  # можно установить снаружи для оповещений

    # ----------------------------------------------------------------
    # Методы для запуска и остановки встроенного цикла
    # ----------------------------------------------------------------
    async def run(self, interval_seconds: int = 30, duration_seconds: int = 5 * 60):
        """
        Запускает цикл health‑чека:
         - подключается к бирже,
         - проверяет состояние каждые interval_seconds,
         - работает до duration_seconds или вызова stop().
        """
        if self._running:
            self._logger.warning("Run already in progress")
            return

        self._running = True
        self._stop_event = asyncio.Event()

        # Попытка подключения
        ok = await self.connect()
        if not ok:
            self._logger.error("Aborting run(): connection failed")
            self._running = False
            return

        start = asyncio.get_event_loop().time()
        self._logger.info(f"Run loop started: interval={interval_seconds}s, duration={duration_seconds}s")

        async def _loop():
            try:
                while self._running and (self._stop_event is None or not self._stop_event.is_set()) and (asyncio.get_event_loop().time() - start) < duration_seconds:
                    await self.check_health()
                    await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                self._logger.info("Run loop cancelled")
            finally:
                await self.close()
                self._logger.info("Run loop finished, session closed")

        self._run_task = asyncio.create_task(_loop())

    async def stop(self):
        """
        Останавливает цикл run().
        """
        if not self._running:
            return
        self._logger.info("Stop requested for run loop")
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        if self._run_task:
            self._run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._run_task

    # ----------------------------------------------------------------
    # Остальные методы (connect, request, get_balance, и т.д.)
    # ----------------------------------------------------------------
    async def connect(self) -> bool:
        """Явное подключение к бирже."""
        self._update_state(ExchangeState.CONNECTING)
        try:
            bal = await self.get_balance("USDT")
            self.balance = bal or Decimal("0")
            self._update_state(ExchangeState.CONNECTED)
            # сразу проверим здоровье
            await self.check_health()
            return True
        except aiohttp.ClientConnectionError:
            self._update_state(ExchangeState.NETWORK_ERROR)
            return False
        except Exception as e:
            self._logger.error(f"Connection failed: {e}")
            self._update_state(ExchangeState.API_ERROR)
            return False

    async def request(self, method: str, path: str, payload: Any = None) -> Tuple[Any, bool]:
        if self._session.closed:
            self._logger.warning("Session was closed, recreating...")
            self._session = Session(timeout=Timeout(total=10))

        url = self._base_url + path
        body = json.dumps(payload, separators=(",", ":")) if method != "GET" and payload else ""
        headers = self._headers(method, path, body)

        for attempt in range(1, 4):
            try:
                async with self._session.request(
                    method, url,
                    headers=headers,
                    data=body if method != "GET" else None,
                    params=payload if method == "GET" else None
                ) as resp:
                    data = await resp.json()
                    self._logger.debug(f"Response: {data}")

                    if resp.status in {429, 502, 503}:
                        retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                        self._logger.warning(f"Retryable error {resp.status}. Wait {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    ok = resp.status == 200 and data.get("code") == "0"
                    if not ok:
                        self._logger.error(f"API error {resp.status}: {data.get('code')} – {data.get('msg')}")

                    return data.get("data", []), ok

            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                self._logger.error(f"Network error [{method} {path}] attempt {attempt}: {e}")
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                self._logger.exception(f"Unexpected error in request: {e}")
                return [], False

        self._logger.error(f"Failed request after 3 attempts: {method} {path}")
        return [], False

    async def get_balance(self, ccy: str = "USDT") -> Optional[Decimal]:
        try:
            data, ok = await self.request("GET", "/api/v5/account/balance")
            if not ok or not isinstance(data, list):
                self._logger.error("Invalid balance response")
                return None

            for account in data:
                if str(account.get("accountType")) == "1":
                    for bal in account.get("details", []):
                        if bal.get("ccy") == ccy:
                            available = Decimal(bal.get("availBal", "0"))
                            self._logger.info(f"Available {ccy}: {available}")
                            return available

            self._logger.warning(f"Currency {ccy} not found")
            return Decimal("0")

        except Exception as e:
            self._logger.exception(f"Error fetching balance: {e}")
            return None

    async def get_symbol_price(self, symbol: str) -> Decimal:
        data, ok = await self.request("GET", "/api/v5/market/ticker", {"instId": symbol})
        if not ok or not data:
            raise ValueError(f"Invalid response for {symbol}: {data}")
        ticker = data[0]
        if "last" not in ticker:
            raise ValueError(f"No 'last' price for {symbol}")
        return Decimal(ticker["last"])

    async def get_symbol_precision(self, symbol: str) -> Tuple[int, int]:
        if symbol in self._symbol_precision_cache:
            return self._symbol_precision_cache[symbol]

        data, ok = await self.request(
            "GET", "/api/v5/public/instruments", {"instType": "SPOT", "instId": symbol}
        )
        if not ok or not data:
            self._logger.warning(f"No precision data for {symbol}")
            return 8, 8

        instr = data[0]
        tick = len(instr["tickSz"].split(".")[-1]) if "." in instr["tickSz"] else 0
        lot = len(instr["lotSz"].split(".")[-1]) if "." in instr["lotSz"] else 0

        self._symbol_precision_cache[symbol] = (tick, lot)
        return tick, lot

    async def place_order(
        self, symbol: str, side: str, price: Decimal, size: Decimal,
        trade_mode: str = "isolated", position_side: str = "long"
    ) -> Optional[str]:
        try:
            px_prec, sz_prec = await self.get_symbol_precision(symbol)
            payload = {
                "instId": symbol,
                "tdMode": trade_mode,
                "side": side,
                "ordType": "limit",
                "px": f"{price:.{px_prec}f}",
                "sz": f"{size:.{sz_prec}f}"
            }
            if trade_mode != "cash":
                payload["posSide"] = position_side

            data, ok = await self.request("POST", "/api/v5/trade/order", payload)
            if ok and data:
                ord_id = data[0].get("ordId")
                self._logger.info(f"Order placed: {ord_id}")
                return ord_id
            return None

        except Exception as e:
            self._logger.exception(f"Error placing order: {e}")
            return None

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        try:
            payload = {"instId": symbol, "ordId": order_id}
            _, ok = await self.request("POST", "/api/v5/trade/cancel-order", payload)
            return ok
        except Exception as e:
            self._logger.error(f"Error canceling order {order_id}: {e}")
            return False

    async def cancel_all_orders(self, symbol: str) -> List[str]:
        try:
            payload = [{"instId": symbol}]
            data, ok = await self.request("POST", "/api/v5/trade/cancel-batch-orders", payload)
            canceled = [item["ordId"] for item in data if "ordId" in item] if ok else []
            self._logger.info(f"Canceled orders: {canceled}")
            return canceled
        except Exception as e:
            self._logger.error(f"Error canceling all orders: {e}")
            return []

    async def check_health(self):
        """Проверяет соединение, баланс и цены."""
        try:
            if self._state in {ExchangeState.DISCONNECTED, ExchangeState.NETWORK_ERROR}:
                await self.connect()

            bal = await self.get_balance("USDT")
            if bal is None:
                self._update_state(ExchangeState.API_ERROR)
                return
            self.balance = bal
            if self.balance < Decimal("10"):
                self._update_state(ExchangeState.BALANCE_LOW)
            else:
                self._update_state(ExchangeState.ACTIVE)

            for sym in self._symbols:
                price = await self.get_symbol_price(sym)
                if price <= 0:
                    self._update_state(ExchangeState.API_ERROR)
                    return

        except aiohttp.ClientConnectionError:
            self._update_state(ExchangeState.NETWORK_ERROR)
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                self._update_state(ExchangeState.RATE_LIMITED)
            else:
                self._update_state(ExchangeState.API_ERROR)
        except Exception:
            self._logger.exception("Health check failed")
            self._update_state(ExchangeState.UNKNOWN)

    async def get_status_report(self) -> dict:
        return {
            "state": self._state.name,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "balance": str(getattr(self, "balance", None)),
            "is_operational": self._state in {
                ExchangeState.ACTIVE,
                ExchangeState.CONNECTED,
                ExchangeState.BALANCE_LOW
            },
            "needs_attention": self._state in self._critical_states,
            "state_history": self._get_recent_history()
        }

    async def place_test_order(self) -> Optional[str]:
        """Тестовый ордер для health check."""
        if not self._symbols:
            return None
        return await self.place_order(
            symbol=self._symbols[0],
            side="buy",
            price=Decimal("0"),
            size=Decimal("0")
        )

    async def handle_rate_limit(self):
        """Обработка превышения rate limit."""
        self._logger.warning("Rate limit detected, pausing operations")
        await asyncio.sleep(60)
        self._update_state(ExchangeState.CONNECTED)
        await self.check_health()

    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        message = f"{timestamp}{method.upper()}{path}{body}"
        mac = hmac.new(self._secret_key.encode(), message.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        return {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": self._sign(timestamp, method, path, body),
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json",
            **({"x-simulated-trading": "1"} if self._mode else {})
        }

    def _update_state(self, new_state: ExchangeState):
        """Обновление состояния с историей и уведомлениями."""
        if self._state != new_state:
            now = datetime.utcnow()
            self._state_history.append({
                "timestamp": now,
                "from": self._state.name,
                "to": new_state.name
            })
            self._state = new_state
            self._last_update = now
            self._logger.info(f"State changed: {self._state.name}")

            if new_state in self._critical_states and self._notifier:
                asyncio.create_task(
                    self._notifier.send_alert(f"State changed to {self._state.name}")
                )

    def _get_recent_history(self, count: int = 5) -> List[Dict[str, str]]:
        return [
            {
                "timestamp": h["timestamp"].isoformat(),
                "from": h["from"],
                "to": h["to"]
            }
            for h in self._state_history[-count:]
        ]
