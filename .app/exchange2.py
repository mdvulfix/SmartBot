# === file: exchange.py ===
import time
import hmac
import hashlib
import base64
import aiohttp
import asyncio
import json
import logging
from decimal import Decimal
from typing import Optional, Dict, Any

logger = logging.getLogger("SmartBot_v1")

class OkxExchange:
    def __init__(self, api_key: str, secret_key: str, passphrase: str, demo: bool = False):
        self._api_key = api_key
        self._secret_key = secret_key
        self._passphrase = passphrase
        self._base_url = "https://www.okx.com"
        self._demo = demo
        self._session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_semaphore = asyncio.Semaphore(10)  # Ограничение 10 запросов в секунду

    async def enter(self):
        await self.create_session()
        return self

    async def exit(self, exc_type, exc_val, exc_tb):
        await self.close_session()

    async def create_session(self):
        """Создание клиентской сессии"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                json_serialize=json.dumps
            )

    async def close_session(self):
        """Закрытие клиентской сессии"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def request_with_retry(self, 
                               method: str, 
                               path: str, 
                               payload: Optional[Dict] = None,
                               max_retries: int = 3,
                               backoff_factor: float = 0.5) -> Dict[str, Any]:
        """Выполнение запроса с повторными попытками"""
        await self.create_session()
        body = json.dumps(payload) if payload else ""
        headers = self.get_headers(method, path, body)
        url = self._base_url + path

        async with self._rate_limit_semaphore:
            for attempt in range(max_retries):
                try:
                    async with self._session.request(
                        method, url, headers=headers, data=body
                    ) as response:
                        data = await response.json(loads=json.loads)

                        if response.status == 200:
                            return {"success": True, "data": data.get("data", [])}
                        else:
                            error_msg = data.get("msg", "Unknown error")
                            logger.error(f"Request failed (attempt {attempt+1}): {error_msg}")
                            
                            # Проверка лимитов запросов
                            if response.status == 429:
                                retry_after = int(response.headers.get('Retry-After', 1))
                                await asyncio.sleep(retry_after)
                            else:
                                await asyncio.sleep(backoff_factor * (2 ** attempt))

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(f"Network error (attempt {attempt+1}): {str(e)}")
                    await asyncio.sleep(backoff_factor * (2 ** attempt))
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {str(e)}")
                    return {"success": False, "error": "Invalid JSON response"}

        return {"success": False, "error": "Max retries exceeded"}

    async def get_balance(self, ccy: str = "USDT") -> Decimal:
        """Получение доступного баланса"""
        endpoint = "/api/v5/account/balance"
        res = await self.request_with_retry("GET", endpoint)
        
        if not res['success']:
            logger.error("Failed to fetch balance")
            return Decimal('0')

        for acc in res['data'][0]['details']:
            if acc['ccy'] == ccy:
                bal = Decimal(acc['availBal'])
                logger.info(f"Available {ccy}: {bal}")
                return bal
        
        logger.error(f"Currency {ccy} not found in balance")
        return Decimal('0')

    async def get_current_price(self, symbol: str) -> Decimal:
        """Получение текущей цены"""
        endpoint = f"/api/v5/market/ticker?instId={symbol}"
        res = await self.request_with_retry("GET", endpoint)
        
        if res['success'] and res['data']:
            return Decimal(res['data'][0]['last'])
        
        logger.error("Failed to fetch current price")
        raise ValueError("Could not get current price")

    async def place_order(self, 
                         symbol: str,
                         side: str,
                         price: Decimal,
                         size: Decimal,
                         order_type: str = "limit") -> Optional[str]:
        """Размещение ордера"""
        endpoint = "/api/v5/trade/order"
        payload = {
            "instId": symbol,
            "tdMode": "isolated",
            "side": side,
            "ordType": order_type,
            "px": str(price),
            "sz": str(size)
        }
        
        res = await self.request_with_retry("POST", endpoint, payload)
        if res['success']:
            return res['data'][0]['ordId']
        return None

    async def cancel_all_orders(self, symbol: str) -> bool:
        """Отмена всех активных ордеров"""
        endpoint = "/api/v5/trade/cancel-all-orders"
        payload = {"instId": symbol}
        res = await self.request_with_retry("POST", endpoint, payload)
        return res['success']
    
    def sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """Генерация подписи запроса"""
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(
            self._secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode('utf-8')

    def get_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """Получение заголовков для запроса"""
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
        signature = self.sign(timestamp, method, path, body)
        headers = {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json"
        }
        if self._demo:
            headers["x-simulated-trading"] = "1"
        return headers