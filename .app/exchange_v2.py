# === file: exchange.py ===

import os
import time
import hmac
import hashlib
import base64
import json
import asyncio

from utils import Utils
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Tuple, Optional
from logging import Logger
from aiohttp import ClientSession as Session
from aiohttp import ClientTimeout as Timeout

class Exchange(ABC):
    
    @abstractmethod
    async def request(self, method: str, path: str, payload=None) -> Tuple[Any, bool]:
        pass

    @abstractmethod
    async def get_balance(self, ccy: str = "USDT") -> Decimal:
        pass

    @abstractmethod
    async def close(self):
        pass

class OkxExchange(Exchange):
    def __init__(self):
        self._logger = Utils.get_logger("okx_exchange")
        
        config_path = os.path.join(os.path.dirname(__file__), "okx_config.json")
        if not os.path.exists(config_path):
            self._logger.error(f"Missing config file: {config_path}")
            raise FileNotFoundError(f"Missing config file: {config_path}")

        with open(config_path, "r") as config_file:
            config = json.load(config_file)

        self._api_key = config.get("api_key")
        self._secret_key = config.get("secret_key")
        self._passphrase = config.get("passphrase")
        self._mode = config.get("demo", True)
        self._base_url = "https://www.okx.com" if not self._mode else "https://www.okx.com/simulated/v5"
        self._session = Session()
        
    async def request(self, method, path, payload=None):
        body = json.dumps(payload) if payload else ""
        url = self._base_url + path
        headers = self._headers(method, path, body)
        for _ in range(3):
            try:
                async with self._session.request(method, url, headers=headers, data=body, timeout=Timeout(total=10)) as resp:
                    data = await resp.json()
                    ok = resp.status == 200 and data.get("code") == "0"
                    return data.get("data", []), ok
            except Exception as e:
                self._logger.error(f"Request error [{method} {path}]: {e}")
                await asyncio.sleep(1)
        return [], False

    async def get_balance(self, ccy="USDT") -> Decimal:
        data, ok = await self.request("GET", "/api/v5/account/balance")
        self._logger.debug(f"Raw balance response: ok={ok}, data={data}")
        if not ok:
            self._logger.error("Failed to fetch balance")
            return Decimal('0')
        for account in data[0].get('details', []):
            if account.get('ccy') == ccy:
                balance = Decimal(account.get('availBal', '0'))
                self._logger.info(f"Available {ccy}: {balance}")
                return balance
        return Decimal('0')

    async def close(self):
        await self._session.close()

    def _sign(self, timestamp, method, path, body):
        message = f"{timestamp}{method}{path}{body}"
        mac = hmac.new(self._secret_key.encode(), message.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method, path, body=""):
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
        sign = self._sign(timestamp, method, path, body)
        headers = {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json"
        }
        if self._base_url.endswith("/v5"):
            headers["x-simulated-trading"] = "1"
        return headers



