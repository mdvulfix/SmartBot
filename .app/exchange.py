# === file: exchange.py ===

import os
import time
import hmac
import hashlib
import base64
import json
import asyncio
import contextlib
import aiohttp
from enum import Enum, auto
from abc import ABC, abstractmethod
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Tuple, Optional, List, Dict
from aiohttp import ClientSession as Session
from aiohttp import ClientTimeout as Timeout
from utils import Utils

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
    async def place_order(self, symbol: str, side: str, price: Decimal, size: Decimal, trade_mode: str = "isolated", position_side: str = "long") -> Optional[str]:
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

    @abstractmethod
    async def run(self, interval_seconds: int = 30, duration_seconds: int = 5 * 60):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    async def get_status_report(self) -> Dict[str, Any]:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

CHECK_HEALTH_INTERVAL = 120  # seconds
RUN_DURATION_SECONDS = 5 * 60  # 5 minutes

class OkxExchange(Exchange):
    def __init__(self, symbols: Optional[List[str]] = None):
        self._logger = Utils.get_logger("okx_exchange")

        # Load config
        config_path = os.path.join(os.path.dirname(__file__), "okx_config.json")
        if not os.path.exists(config_path):
            self._logger.error(f"Missing config file: {config_path}")
            raise FileNotFoundError(config_path)

        with open(config_path, "r") as f:
            cfg = json.load(f)

        self._api_key = cfg["api_key"].strip()
        self._secret_key = cfg["secret_key"].strip()
        self._passphrase = cfg["passphrase"].strip()

        if not all([self._api_key, self._secret_key, self._passphrase]):
            raise ValueError("Missing API credentials in okx_config.json")

        self._symbols: List[str] = cfg.get("symbols", [])
        # если список symbols передан в конструктор — используем его,
        # иначе — берём из конфига
        if symbols:
            self._symbols = symbols
        else:
            self._symbols: List[str] = cfg.get("symbols", [])

        self._mode = cfg.get("demo", True)
        self._base_url = "https://www.okx.com"
        self._session: Optional[Session] = None

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
        self._stop_event: Optional[asyncio.Event] = None
        self._run_task: Optional[asyncio.Task] = None

        # Log mode
        if self._mode:
            self._logger.info("Running in DEMO mode")
        else:
            self._logger.warning("Running in LIVE TRADING mode")

        self._notifier = None


    # ----------------------------------------------------------------
    # Run / Stop methods
    # ----------------------------------------------------------------

    async def run(self, interval_seconds: int = CHECK_HEALTH_INTERVAL, duration_seconds: int = RUN_DURATION_SECONDS):
        if self._run_task and not self._run_task.done():
            self._logger.warning("Run loop already active")
            return

        self._stop_event = asyncio.Event()

        if not await self.connect():
            self._logger.error("Run aborted: could not connect")
            return

        start = asyncio.get_event_loop().time()
        self._logger.info(f"Run loop started: interval={interval_seconds}s, duration={duration_seconds}s")

        async def _loop():
            try:
                while self._stop_event and not self._stop_event.is_set() and (asyncio.get_event_loop().time() - start) < duration_seconds:
                    await self.check_health()
                    await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                self._logger.info("Run loop cancelled")
            finally:
                await self.close()
                self._logger.info("Run loop finished")

        self._run_task = asyncio.create_task(_loop())

    async def stop(self):
        if not self._run_task or self._run_task.done():
            await self.close()
            return
        self._logger.info("Stopping run loop")
        if self._stop_event:
            self._stop_event.set()
        self._run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._run_task
        await self.close() 

    # ----------------------------------------------------------------
    # Connection and health
    # ----------------------------------------------------------------

    async def connect(self) -> bool:
        self._update_state(ExchangeState.CONNECTING)
        try:
            # Recreate session
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = Session(timeout=Timeout(total=10))

            bal = await self.get_balance("USDT")
            self.balance = bal or Decimal("0")
            self._update_state(ExchangeState.CONNECTED)
            return True
        except aiohttp.ClientConnectionError:
            self._update_state(ExchangeState.NETWORK_ERROR)
            return False
        except Exception as e:
            self._logger.error(f"Connection failed: {e}")
            self._update_state(ExchangeState.API_ERROR)
            return False

    async def check_health(self):
        """Проверка соединения, баланса и данных по символам."""
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

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._logger.info("Session closed")
        self._session = None
        self._update_state(ExchangeState.DISCONNECTED)

    # ----------------------------------------------------------------
    # Core API methods
    # ----------------------------------------------------------------

    async def request(self, method: str, path: str, payload: Any = None) -> Tuple[Any, bool]:
        if not self._session or self._session.closed:
            self._session = Session(timeout=Timeout(total=10))

        url = self._base_url + path
        body = json.dumps(payload, separators=(",", ":")) if method != "GET" and payload else ""
        ts = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        signature = self._sign(ts, method, path, body)
        headers = {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json",
            **({"x-simulated-trading": "1"} if self._mode else {})
        }

        for attempt in range(1, 4):
            try:
                async with self._session.request(
                    method, url,
                    params=payload if method == "GET" else None,
                    json=payload if method in ("POST", "PUT") else None,
                    headers=headers
                ) as resp:
                    data = await resp.json()
                    self._logger.debug(f"Response: {data}")

                    if resp.status in {429, 502, 503}:
                        retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                        self._logger.warning(f"Retryable {resp.status}, waiting {retry_after}s")
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
                self._logger.exception(f"Unexpected error: {e}")
                return [], False

        self._logger.error(f"Failed after 3 attempts: {method} {path}")
        return [], False

    async def get_balance(self, ccy: str = "USDT") -> Optional[Decimal]:
        """
        Fetch balances for all account types, log each,
        and return the available balance for the requested currency.
        """
        data, ok = await self.request("GET", "/api/v5/account/balance")
        if not ok or not isinstance(data, list):
            self._logger.error("Invalid balance response")
            return None

        found: Optional[Decimal] = None

        for acct in data:
            acct_type = acct.get("accountType")
            # Собираем все валюты этого аккаунта
            balances = {
                bal.get("ccy"): bal.get("availBal")
                for bal in acct.get("details", [])
            }
            self._logger.info(f"AccountType={acct_type} balances: {balances}")

            # Если среди них есть нужная валюта — запоминаем
            if ccy in balances:
                try:
                    found = Decimal(balances[ccy])
                except Exception:
                    self._logger.error(f"Cannot parse balance for {ccy}: {balances[ccy]}")
                    found = Decimal("0")

        if found is not None:
            self._logger.info(f"Available {ccy}: {found}")
            return found

        self._logger.warning(f"Currency {ccy} not found in any accountType")
        return Decimal("0")

    async def get_symbol_price(self, symbol: str) -> Decimal:
        data, ok = await self.request("GET", "/api/v5/market/ticker", {"instId": symbol})
        if not ok or not data:
            raise ValueError(f"Invalid response for {symbol}: {data}")
        return Decimal(data[0]["last"])

    async def get_symbol_precision(self, symbol: str) -> Tuple[int, int]:
        if symbol in self._symbol_precision_cache:
            return self._symbol_precision_cache[symbol]

        data, ok = await self.request(
            "GET", "/api/v5/public/instruments",
            {"instType": "SPOT", "instId": symbol}
        )
        if not ok or not data:
            return 8, 8

        instr = data[0]
        tick = len(instr["tickSz"].split(".")[-1]) if "." in instr["tickSz"] else 0
        lot = len(instr["lotSz"].split(".")[-1]) if "." in instr["lotSz"] else 0

        self._symbol_precision_cache[symbol] = (tick, lot)
        return tick, lot

    async def place_order(self, symbol: str, side: str, price: Decimal, size: Decimal, trade_mode: str = "isolated", position_side: str = "long") -> Optional[str]:
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

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        _, ok = await self.request(
            "POST", "/api/v5/trade/cancel-order",
            {"instId": symbol, "ordId": order_id}
        )
        return ok

    async def cancel_all_orders(self, symbol: str) -> List[str]:
        data, ok = await self.request(
            "POST", "/api/v5/trade/cancel-batch-orders",
            [{"instId": symbol}]
        )
        canceled = [item["ordId"] for item in data if "ordId" in item] if ok else []
        self._logger.info(f"Canceled orders: {canceled}")
        return canceled

    # ----------------------------------------------------------------
    # Status methods
    # ----------------------------------------------------------------

    async def get_status_report(self) -> Dict[str, Any]:
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

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------
    
    def _sign(self, timestamp: str, method: str, path: str, body: str) -> str:
        message = f"{timestamp}{method.upper()}{path}{body}"
        self._logger.debug(f"Signing message: {message}")
        mac = hmac.new(self._secret_key.encode(), message.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _update_state(self, new_state: ExchangeState):
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
                asyncio.create_task(self._notifier.send_alert(
                    f"State changed to {self._state.name}"
                ))

    def _get_recent_history(self, count: int = 5) -> List[Dict[str, str]]:
        return [
            {
                "timestamp": h["timestamp"].isoformat(),
                "from": h["from"],
                "to": h["to"]
            }
            for h in self._state_history[-count:]
        ]
