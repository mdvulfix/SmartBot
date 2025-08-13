# === file: exchange.py ===

import hmac, hashlib, base64, json, asyncio, aiohttp, contextlib
from enum import Enum, auto
from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
from typing import Any, Tuple, Optional, List, Dict
from aiohttp import ClientSession as Session, ClientTimeout as Timeout
from utils import Utils
from coin import Coin 

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
    async def _request(self, method: str, path: str, payload: Any = None) -> Tuple[Any, bool]:
        pass

    @abstractmethod
    async def get_balance(self, coin: Coin) -> Optional[Decimal]:
        pass

    @abstractmethod
    async def get_symbol_price(self, coin: Coin) -> Decimal:
        pass

    @abstractmethod
    async def place_limit_order_by_size(self, coin: Coin, side: str, price: Decimal, size: Optional[Decimal], trade_mode: str) -> Optional[str]:
        pass

    @abstractmethod
    async def place_limit_order_by_amount(self, coin: Coin, side: str, price: Decimal, notional: Optional[Decimal], trade_mode: str) -> Optional[str]:
        pass

    @abstractmethod
    async def cancel_order(self, coin: Coin, order_id: str) -> bool:
        pass

    @abstractmethod
    async def cancel_all_orders(self, coin: Coin) -> List[str]:
        pass

    @abstractmethod
    async def close(self):
        pass

    @abstractmethod
    async def run(self, interval: int, duration: int):
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

class OkxExchange(Exchange):
    
    CHECK_HEALTH_INTERVAL_SECONDS = 120  # seconds
    RUN_DURATION_SECONDS = 5 * 60  # 5 minutes

    def __init__(self, config: Any, demo: bool):
        self._logger = Utils.get_logger("okx_exchange")

        # load config
        self._api_key = config["api_key"].strip()
        self._secret_key = config["secret_key"].strip()
        self._passphrase = config["passphrase"].strip()
        

        if not all([self._api_key, self._secret_key, self._passphrase]):
            raise ValueError("Missing API credentials in okx_config.json")

        self._base_url = "https://www.okx.com"
        
        # session
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

        # run/stop control
        self._stop_event: Optional[asyncio.Event] = None
        self._run_task: Optional[asyncio.Task] = None
        self._closing = False  # Флаг закрытия

        # log mode
        self._demo = demo

        if self._demo:
            self._logger.info("Running in DEMO mode")
        else:
            self._logger.warning("Running in LIVE TRADING mode")

        self._notifier = None
        self._balance = Decimal("0")

    # ----------------------------------------------------------------
    # Run / Stop
    # ----------------------------------------------------------------
    async def run(self, interval: int = CHECK_HEALTH_INTERVAL_SECONDS, duration: int = RUN_DURATION_SECONDS):
        if self._closing or (self._run_task and not self._run_task.done()):
            self._logger.warning("Run loop already active or exchange is closing")
            return

        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        else:
            self._stop_event.clear()
        
        if not await self.connect():
            self._logger.error("Run aborted: could not connect")
            return

        start = asyncio.get_event_loop().time()
        self._logger.info(f"Run loop started: interval={interval}s, duration={duration}s")

        async def _loop():
            try:
                while self._stop_event is not None and not self._stop_event.is_set() and (asyncio.get_event_loop().time() - start) < duration:
                    if self._closing:
                        break
                    await self.check_health()
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                self._logger.info("Run loop cancelled")
            finally:
                if not self._closing:
                    await self.close()
                self._logger.info("Run loop finished")

        self._run_task = asyncio.create_task(_loop())

    async def stop(self):
        if self._closing or not self._run_task or self._run_task.done():
            return
        self._logger.info("Stopping run loop")
        if self._stop_event is not None:
            self._stop_event.set()
        self._run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._run_task

    # ----------------------------------------------------------------
    # Connection / Health
    # ----------------------------------------------------------------
    async def connect(self) -> bool:
        if self._closing:
            return False
            
        self._update_state(ExchangeState.CONNECTING)
        try:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = Session(timeout=Timeout(total=10))

            balance = await self.get_balance(Coin("USDT"))
            self._balance = balance or Decimal("0")
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
            if self._closing:
                return
                
            if self._state in {ExchangeState.DISCONNECTED, ExchangeState.NETWORK_ERROR}:
                await self.connect()

            balance = await self.get_balance(Coin("USDT"))
            if balance is None:
                self._update_state(ExchangeState.API_ERROR)
                return
            self._balance = balance

            if self._balance < Decimal("10"):
                self._update_state(ExchangeState.BALANCE_LOW)
            else:
                self._update_state(ExchangeState.ACTIVE)

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
        if self._closing:
            return
            
        self._closing = True
        
        # Остановить фоновые задачи
        await self.stop()
        
        # Закрыть сессию
        if self._session and not self._session.closed:
            await self._session.close()
            self._logger.info("Session closed")
        self._session = None
        self._update_state(ExchangeState.DISCONNECTED)

    # ----------------------------------------------------------------
    # Core API
    # ----------------------------------------------------------------
    
    async def get_balance(self, coin: Coin) -> Optional[Decimal]:
        if self._closing:
            return None
            
        data, ok = await self._request("GET", "/api/v5/account/balance")
        if not ok or not isinstance(data, list) or not data:
            self._logger.error("Invalid balance response")
            return None

        # Обрабатываем структуру ответа OKX
        try:
            for account in data:
                details = account.get("details", [])
                for detail in details:
                    if detail.get("ccy") == coin.symbol:
                        available_balance = detail.get("availBal", "0")
                        return Decimal(available_balance)
        except Exception as e:
            self._logger.error(f"Error parsing balance: {e}")
        
        self._logger.warning(f"Currency {coin.symbol} not found in balance data")
        return Decimal("0")

    async def get_symbol_price(self, coin: Coin) -> Decimal:
        if self._closing:
            return Decimal("0")
            
        data, ok = await self._request("GET", "/api/v5/market/ticker", {"instId": coin.symbol_id})
        if not ok or not data or not isinstance(data, list):
            self._logger.error(f"Invalid ticker response for {coin.symbol}")
            return Decimal("0")
        
        try:
            last_price = data[0].get("last")
            return Decimal(last_price) if last_price else Decimal("0")
        except Exception as e:
            self._logger.error(f"Error parsing price for {coin.symbol}: {e}")
            return Decimal("0")

    async def get_symbol_details(self, coin: Coin) -> Dict[str, Any]:
        """Получает и кэширует параметры инструмента"""
        if self._closing:
            return {
                "minSz": Decimal("0.01"),
                "lotSz": Decimal("0.01"),
                "tickSz": Decimal("0.01"),
                "ctVal": Decimal("1"),
                "ctType": "linear"
            }
            
        symbol = coin.symbol
        
        if symbol in Coin.SYMBOL_CACHE:
            return Coin.SYMBOL_CACHE[symbol]

        # Определяем тип инструмента по символу
        symbol_type = "SWAP"
        data, ok = await self._request("GET", "/api/v5/public/instruments", {"instType": symbol_type, "instId": coin.symbol_id})
        
        if not ok or not data or not isinstance(data, list):
            self._logger.error(f"Failed to get instrument details for {symbol}")
            return {
                "minSz": Decimal("0.01"),
                "lotSz": Decimal("0.01"),
                "tickSz": Decimal("0.01"),
                "ctVal": Decimal("1"),
                "ctType": "linear"
            }

        try:
            symbol_data = data[0]
            symbol_details = {
                "minSz": Decimal(symbol_data.get("minSz", "0.01")),
                "lotSz": Decimal(symbol_data.get("lotSz", "0.01")),
                "tickSz": Decimal(symbol_data.get("tickSz", "0.01")),
                "ctVal": Decimal(symbol_data.get("ctVal", "1")),
                "ctType": symbol_data.get("ctType", "linear")
            }
            Coin.SYMBOL_CACHE[symbol] = symbol_details
            return symbol_details
        
        except Exception as e:
            self._logger.error(f"Error parsing instrument details: {e}")
            return {
                "minSz": Decimal("0.01"),
                "lotSz": Decimal("0.01"),
                "tickSz": Decimal("0.01"),
                "ctVal": Decimal("1"),
                "ctType": "linear"
            }
        
    async def place_limit_order_by_size(self, coin: Coin, side: str, price: Decimal, size: Optional[Decimal], trade_mode: str = "isolated") -> Optional[str]:
        if self._closing:
            return None

        details = await self.get_symbol_details(coin)
        min_size = details["minSz"]
        lot_size = details["lotSz"]
        tick_size = details["tickSz"]

        if size is None:
            self._logger.error("Size must be specified")
            return None
        
        # Корректировка минимального размера
        size = (size // lot_size) * lot_size
        if size < min_size:
            self._logger.info(f"Size adjusted to minimum: {size} -> {min_size}")
            size = min_size

        # Корректировка цены
        price = (price // tick_size) * tick_size

        # Формирование запроса
        order = {
            "instId": coin.symbol_id,
            "tdMode": trade_mode,
            "side": side.lower(),
            "ordType": "limit",
            "px": str(price),
            "sz": str(size),
        }

        self._logger.info(f"Placing order: {coin.symbol} {side} {price} {size}")

        data, ok = await self._request("POST", "/api/v5/trade/order", order)
        if ok and data and isinstance(data, list):
            order_id = data[0].get("ordId")
            if order_id:
                self._logger.info(f"Order placed: {order_id}")
                return order_id

        self._logger.error(f"Order failed: {data}")
        return None

    async def place_limit_order_by_amount(self, coin: Coin, side: str, price: Decimal, notional: Optional[Decimal], trade_mode: str = "isolated") -> Optional[str]:
        if self._closing:
            return None

        details = await self.get_symbol_details(coin)
        min_size = details["minSz"]
        lot_size = details["lotSz"]
        tick_size = details["tickSz"]
        ctVal = details["ctVal"]
        ctType = details["ctType"]

        if notional is None:
            self._logger.error("Notional must be specified")
            return None
            
        if ctType == "inverse":
            self._logger.error("Notional calculation not supported for inverse contracts")
            return None
        
        # Расчет размера по номиналу    
        size = notional / (price * ctVal)
            
        # Корректировка размера и цены
        size = (size // lot_size) * lot_size
        
        price = (price // tick_size) * tick_size
        if price <= 0:
            self._logger.error("Invalid price")
            return None

        # Формирование запроса
        order = {
            "instId": coin.symbol_id,
            "tdMode": trade_mode,
            "side": side.lower(),
            "ordType": "limit",
            "px": str(price),
            "sz": str(size),
        }

        self._logger.info(f"Placing order: {coin.symbol} {side} {price} {size}")

        data, ok = await self._request("POST", "/api/v5/trade/order", order)
        if ok and data and isinstance(data, list):
            order_id = data[0].get("ordId")
            if order_id:
                self._logger.info(f"Order placed: {order_id}")
                return order_id

        self._logger.error(f"Order failed: {data}")
        return None

    async def cancel_order(self, coin: Coin, order_id: str) -> bool:
        if self._closing:
            return False
            
        order = {"instId": coin.symbol_id, "ordId": order_id}
        data, ok = await self._request("POST", "/api/v5/trade/cancel-order", order)

        if ok:
            self._logger.info(f"Order cancelled: {order_id}")
            return True
        
        self._logger.error(f"Cancel failed: {data}")
        return False
        
    async def cancel_all_orders(self, coin: Coin) -> List[str]:
        if self._closing:
            return []
            
        # Получаем активные ордера
        data, ok = await self._request("GET", "/api/v5/trade/orders-pending", {"instId": coin.symbol_id})
        if not ok or not data:
            return []

        # Формируем список ордеров для отмены
        orders_to_cancel = [{"instId": coin.symbol_id, "ordId": order["ordId"]} for order in data]
        
        if not orders_to_cancel:
            return []

        # Отменяем пачкой
        cancel_data, ok = await self._request("POST", "/api/v5/trade/cancel-batch-orders", orders_to_cancel)
        if not ok:
            return []

        # Собираем успешно отмененные ордера
        canceled = [item["ordId"] for item in cancel_data if item.get("sCode") == "0"]
        self._logger.info(f"Canceled {len(canceled)} orders")
        return canceled

    async def get_status_report(self) -> Dict[str, Any]:
        return {
            "state": self._state.name,
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "balance": str(self._balance),
            "is_operational": self._state in {
                ExchangeState.ACTIVE,
                ExchangeState.CONNECTED,
                ExchangeState.BALANCE_LOW,
            },
            "needs_attention": self._state in self._critical_states,
            "state_history": self._get_recent_history(),
        }

    async def _request(self, method: str, path: str, payload: Any = None) -> Tuple[Any, bool]:
        if self._closing:
            self._logger.warning("Skipping request, exchange is closing")
            return [], False
            
        if not self._session or self._session.closed:
            self._session = Session(timeout = Timeout(total = 10))

        url = self._base_url + path

        # Prepare query parameters for GET requests
        if method.upper() == "GET" and payload:
            # Сортируем параметры и кодируем их
            sorted_params = sorted(payload.items(), key=lambda x: x[0])
            encoded_params = "&".join(f"{k}={v}" for k, v in sorted_params)
            full_url = f"{url}?{encoded_params}"
            body = ""
        else:
            full_url = url
            body = json.dumps(payload, separators=(",", ":")) if payload else ""
            encoded_params = ""

        # Для подписи используем полный путь с параметрами для GET
        sign_path = f"{path}?{encoded_params}" if method.upper() == "GET" and payload else path

        # Генерируем timestamp в правильном формате
        now = datetime.now(timezone.utc)
        timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{now.microsecond // 1000:03d}Z"
        
        # Формируем сообщение для подписи
        message = f"{timestamp}{method.upper()}{sign_path}{body}"
        self._logger.debug(f"Signing message: {message}")
        
        # Создаем подпись
        signature = base64.b64encode(
            hmac.new(
                self._secret_key.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')

        headers = {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json",
            **({"x-simulated-trading": "1"} if self._demo else {}),
        }
        if body:
            headers["Content-Length"] = str(len(body))

        for attempt in range(1, 4):
            try:
                request_params = {
                    "method": method,
                    "url": full_url,
                    "headers": headers,
                    "timeout": Timeout(total=10)
                }

                if method.upper() == "POST" and body:
                    request_params["data"] = body
                elif method.upper() == "GET" and payload:
                    # Для GET параметры уже в URL
                    pass
                else:
                    request_params["json"] = payload if payload else None

                async with self._session.request(**request_params) as resp:
                    data = await resp.json()
                    self._logger.debug(f"Response: {data}")

                    if resp.status in {429, 502, 503}:
                        retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                        self._logger.warning(f"Retryable {resp.status}, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue

                    ok = (resp.status == 200 and data.get("code") == "0")
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
    
    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------
    
    def _update_state(self, new_state: ExchangeState):
        if self._state != new_state:
            now = datetime.now(timezone.utc)
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