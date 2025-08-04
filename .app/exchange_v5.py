import os
import hmac
import hashlib
import base64
import json
import asyncio
import contextlib
import aiohttp
from enum import Enum, auto
from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
from typing import Any, Tuple, Optional, List, Dict
from aiohttp import ClientSession as Session, ClientTimeout as Timeout
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
    async def place_order(
        self,
        symbol: str,
        side: str,
        price: Decimal,
        size: Optional[Decimal] = None,
        notional: Optional[Decimal] = None,
        trade_mode: str = "isolated"
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

        # load config
        config_path = os.path.join(os.path.dirname(__file__), "okx_config.json")
        if not os.path.exists(config_path):
            self._logger.error(f"Missing config file: {config_path}")
            raise FileNotFoundError(config_path)

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self._api_key = cfg["api_key"].strip()
        self._secret_key = cfg["secret_key"].strip()
        self._passphrase = cfg["passphrase"].strip()
        self._mode = cfg.get("demo", True)

        if not all([self._api_key, self._secret_key, self._passphrase]):
            raise ValueError("Missing API credentials in okx_config.json")

        self._symbols = symbols or cfg.get("symbols", [])
        self._base_url = "https://www.okx.com"
        self._session: Optional[Session] = None

        # state machine
        self._state = ExchangeState.DISCONNECTED
        self._state_history: List[Dict[str, Any]] = []
        self._last_update: Optional[datetime] = None
        self._critical_states = {
            ExchangeState.API_ERROR,
            ExchangeState.NETWORK_ERROR,
            ExchangeState.ORDER_ERROR,
            ExchangeState.MAINTENANCE,
        }

        # precision cache
        self._symbol_precision_cache: Dict[str, Tuple[int, int]] = {}

        # run/stop control
        self._stop_event: Optional[asyncio.Event] = None
        self._run_task: Optional[asyncio.Task] = None

        # log mode
        if self._mode:
            self._logger.info("Running in DEMO mode")
        else:
            self._logger.warning("Running in LIVE TRADING mode")

        self._notifier = None

    # ----------------------------------------------------------------
    # Run / Stop
    # ----------------------------------------------------------------
    async def run(self, interval_seconds: int = CHECK_HEALTH_INTERVAL, duration_seconds: int = RUN_DURATION_SECONDS):
        if self._run_task and not self._run_task.done():
            self._logger.warning("Run loop already active")
            return

        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        if not await self.connect():
            self._logger.error("Run aborted: could not connect")
            return

        start = asyncio.get_event_loop().time()
        self._logger.info(f"Run loop started: interval={interval_seconds}s, duration={duration_seconds}s")

        async def _loop():
            try:
                while self._stop_event is not None and not self._stop_event.is_set() and (asyncio.get_event_loop().time() - start) < duration_seconds:
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
        if self._stop_event is not None:
            self._stop_event.set()
        self._run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._run_task
        await self.close()

    # ----------------------------------------------------------------
    # Connection / Health
    # ----------------------------------------------------------------
    async def connect(self) -> bool:
        self._update_state(ExchangeState.CONNECTING)
        try:
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
    # Core API
    # ----------------------------------------------------------------
    async def request(self, method: str, path: str, payload: Any = None) -> Tuple[Any, bool]:
        if not self._session or self._session.closed:
            self._session = Session(timeout=Timeout(total=10))

        url = self._base_url + path

        # prepare body and params so signature matches exactly
        if method.upper() == "GET" or payload is None:
            body = ""
            params = payload if method.upper() == "GET" else None
            data = None
        else:
            body = json.dumps(payload, separators=(",", ":"))
            params = None
            data = body

        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        signature = self._sign(ts, method, path, body)

        headers = {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json",
            **({"x-simulated-trading": "1"} if self._mode else {}),
        }
        if body:
            headers["Content-Length"] = str(len(body))

        for attempt in range(1, 4):
            try:
                async with self._session.request(
                    method, url,
                    params=params,
                    data=data,
                    headers=headers,
                    timeout=Timeout(total=10)
                ) as resp:
                    data_json = await resp.json()
                    self._logger.debug(f"Response: {data_json}")

                    if resp.status in {429, 502, 503}:
                        retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                        self._logger.warning(f"Retryable {resp.status}, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    ok = (resp.status == 200 and data_json.get("code") == "0")
                    if not ok:
                        self._logger.error(f"API error {resp.status}: {data_json.get('code')} – {data_json.get('msg')}")
                    return data_json.get("data", []), ok

            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                self._logger.error(f"Network error [{method} {path}] attempt {attempt}: {e}")
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                self._logger.exception(f"Unexpected error: {e}")
                return [], False

        self._logger.error(f"Failed after 3 attempts: {method} {path}")
        return [], False

    async def get_balance(self, ccy: str = "USDT") -> Optional[Decimal]:
        data, ok = await self.request("GET", "/api/v5/account/balance")
        if not ok or not isinstance(data, list):
            self._logger.error("Invalid balance response")
            return None

        found: Optional[Decimal] = None
        for acct in data:
            balances = {bal.get("ccy"): bal.get("availBal") for bal in acct.get("details", [])}
            self._logger.info(f"AccountType={acct.get('accountType')} balances: {balances}")
            if ccy in balances:
                try:
                    found = Decimal(balances[ccy])
                except:
                    self._logger.error(f"Cannot parse balance for {ccy}: {balances[ccy]}")
                    found = Decimal("0")

        if found is not None:
            self._logger.info(f"Available {ccy}: {found}")
            return found

        self._logger.warning(f"Currency {ccy} not found")
        return Decimal("0")

    async def get_symbol_price(self, symbol: str) -> Decimal:
        data, ok = await self.request("GET", "/api/v5/market/ticker", {"instId": symbol})
        if not ok or not data:
            raise ValueError(f"Invalid response for {symbol}: {data}")
        return Decimal(data[0].get("last"))

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
        tick = len(instr.get("tickSz", "0").split(".")[-1])
        lot = len(instr.get("lotSz", "0").split(".")[-1])
        self._symbol_precision_cache[symbol] = (tick, lot)
        return tick, lot

    async def place_order(self, symbol: str, side: str, price: Decimal, size: Optional[Decimal] = None, notional: Optional[Decimal] = None, trade_mode: str = "isolated") -> Optional[str]:
        # if notional given, compute contract size
        if notional is not None:
            inst_data, ok = await self.request("GET", "/api/v5/public/instruments",{"instType": "SWAP", "instId": symbol})
            if not ok or not inst_data:
                self._logger.error(f"Failed to fetch ctVal for {symbol}")
                return None
            ct_val = Decimal(inst_data[0].get("ctVal"))
            raw = notional / (price * ct_val)
            contracts = raw.to_integral_value(rounding=ROUND_DOWN)
            if contracts < 1:
                self._logger.error(f"Notional {notional} too small at price {price}")
                return None
            size = contracts
            self._logger.debug(f"Computed size from notional: {notional} → sz={size}")

        if size is None:
            self._logger.error("Either size or notional must be provided")
            return None

        px_prec, sz_prec = await self.get_symbol_precision(symbol)
        payload = {
            "instId": symbol,
            "tdMode": trade_mode,
            "side": side,
            "ordType": "limit",
            "px": f"{price:.{px_prec}f}",
            "sz": f"{size:.{sz_prec}f}",
            "ccy": "USDT",
        }

        data, ok = await self.request("POST", "/api/v5/trade/order", payload)
        if ok and data:
            ord_id = data[0].get("ordId")
            self._logger.info(f"Order placed: {ord_id}")
            return ord_id

        self._logger.error(f"Order failed: {data}")
        return None

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Отменяем один ордер через single‑endpoint.
        """
        inst_id = symbol if "-" in symbol else f"{symbol}-USDT-SWAP"
        payload = {"instId": inst_id, "ordId": order_id}

        data, ok = await self.request(
            "POST", "/api/v5/trade/cancel-order", payload
        )

        if ok:
            self._logger.info(f"Order cancelled: {order_id}")
            return True
        else:
            self._logger.error(f"Cancel failed: {data}")
            return False
        
    async def cancel_all_orders(self, symbol: str) -> List[str]:
        inst_id = symbol if "-" in symbol else f"{symbol}-USDT-SWAP"
        data, ok = await self.request(
            "POST", "/api/v5/trade/cancel-batch-orders", [{"instId": inst_id}]
        )
        if not ok:
            self._logger.error(f"Cancel all failed: {data}")
            return []
        canceled = [item.get("ordId") for item in data if item.get("sCode") == "0"]
        self._logger.info(f"Canceled all orders: {canceled}")
        return canceled

    async def get_status_report(self) -> Dict[str, Any]:
        return {
            "state": self._state.name,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "balance": str(getattr(self, "balance", None)),
            "is_operational": self._state in {
                ExchangeState.ACTIVE,
                ExchangeState.CONNECTED,
                ExchangeState.BALANCE_LOW,
            },
            "needs_attention": self._state in self._critical_states,
            "state_history": self._get_recent_history(),
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
                "to": new_state.name,
            })
            self._state = new_state
            self._last_update = now
            self._logger.info(f"State changed: {self._state.name}")
            if new_state in self._critical_states and self._notifier:
                asyncio.create_task(self._notifier.send_alert(f"State changed to {self._state.name}"))

    def _get_recent_history(self, count: int = 5) -> List[Dict[str, str]]:
        return [
            {"timestamp": h["timestamp"].isoformat(), "from": h["from"], "to": h["to"]}
            for h in self._state_history[-count:]
        ]
