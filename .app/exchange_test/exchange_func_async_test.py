import aiohttp
import asyncio
import hashlib
import hmac
import base64
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode, quote

class OKXExchange:
    def __init__(self, config_path=None, debug=False):
        self.debug = True
        if config_path is None:
            self.CONFIG_PATH = os.path.join(os.path.dirname(__file__), "okx_config.json")
        else:
            self.CONFIG_PATH = config_path
            
        if not os.path.exists(self.CONFIG_PATH):
            raise FileNotFoundError(f"Missing config file: {self.CONFIG_PATH}")
            
        self._load_config()
        self.BASE_URL = "https://www.okx.com"
        self.HEADER_SIMULATED_TRADING = "1"
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc, tb):
        await self.session.close()
        
    def _load_config(self):
        with open(self.CONFIG_PATH, "r") as f:
            config = json.load(f)
            
        self.api_key = config['api_key']
        self.secret_key = config['secret_key'].strip()
        self.passphrase = config['passphrase'].strip()
        
    def _sign(self, method, endpoint, body=None):
        now = datetime.now(timezone.utc)
        timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{now.microsecond // 1000:03d}Z"
        
        if body:
            body_str = json.dumps(body, separators=(',', ':'))
            message = f"{timestamp}{method}{endpoint}{body_str}"
        else:
            message = f"{timestamp}{method}{endpoint}"
        
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "x-simulated-trading": self.HEADER_SIMULATED_TRADING,
            "Content-Type": "application/json"
        }
        
        return headers, body_str if body else None
        
    async def _request(self, method, endpoint, body=None, params=None):
        if not self.session:
            raise RuntimeError("Session not initialized. Use async with context manager.")
        
        full_endpoint = endpoint
        if method == "GET" and params:
            sorted_params = sorted(params.items(), key=lambda x: x[0])
            encoded_params = urlencode(sorted_params, quote_via=quote)
            full_endpoint += "?" + encoded_params

        headers, body_str = self._sign(method, full_endpoint, body)
        url = self.BASE_URL + endpoint
        
        if self.debug:
            print(f"\n[DEBUG] Request: {method} {url}")
            print(f"[DEBUG] Headers: { {k: v for k, v in headers.items() if k != 'OK-ACCESS-SIGN'} }")
            print(f"[DEBUG] Body: {body_str}")
            print(f"[DEBUG] Params: {params}")
        
        try:
            if method == "GET":
                async with self.session.get(
                    url, 
                    headers=headers, 
                    params=sorted_params if params else None
                ) as response:
                    data = await response.json()
            elif method == "POST":
                async with self.session.post(
                    url, 
                    headers=headers, 
                    data=body_str
                ) as response:
                    data = await response.json()
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if self.debug:
                print(f"[DEBUG] Response: {data}")
            
            if data.get("code") != "0":
                error_msg = f"API error: code={data.get('code')}, msg={data.get('msg')}"
                # Добавим дополнительную информацию из ответа
                if "data" in data and data["data"]:
                    error_details = "\n".join(
                        f"  - [sCode: {item.get('sCode')}] {item.get('sMsg')}" 
                        for item in data["data"] if item.get('sMsg')
                    )
                    if error_details:
                        error_msg += f"\nDetails:\n{error_details}"
                raise Exception(error_msg)
            return data
            
        except aiohttp.ClientError as e:
            error_msg = f"Request failed: {e}"
            if hasattr(e, "response") and e.response:
                try:
                    error_data = await e.response.json()
                    error_msg += f"\nResponse: {error_data}"
                except:
                    error_msg += f"\nResponse text: {await e.response.text()}"
            raise Exception(error_msg)
    
    # Асинхронные методы API
    
    async def place_futures_limit_order(self, symbol, side, price, size, td_mode='cross', pos_side='net', cl_ord_id=''):
        if not isinstance(price, (int, float)) or not isinstance(size, (int, float)):
            raise TypeError("Price and size must be numeric types")

        # Получаем параметры инструмента
        instruments = await self.get_instruments('SWAP')
        instrument = next((item for item in instruments['data'] if item['instId'] == symbol), None)
        
        if not instrument:
            raise ValueError(f"Instrument {symbol} not found")
        
        # Получаем размер лота и минимальный размер
        lot_size = float(instrument['lotSz'])
        min_size = float(instrument['minSz'])
        
        # Корректируем размер ордера
        if size < min_size:
            size = min_size
        else:
            # Округляем до ближайшего кратного lot_size
            size = round(size / lot_size) * lot_size

        endpoint = "/api/v5/trade/order"    
        # Формируем тело запроса с корректным размером
        body = {
            "instId": symbol,
            "tdMode": td_mode,
            "side": side,
            "ordType": "limit",
            "px": str(price),
            "sz": str(size)  # Используем скорректированный размер
        }
        
        if pos_side and pos_side != 'net':
            body["posSide"] = pos_side
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
        
        return await self._request("POST", endpoint, body)



    async def cancel_order(self, ord_id, symbol, cl_ord_id=''):
        """
        Асинхронная отмена ордера
        """
        endpoint = "/api/v5/trade/cancel-order"
        body = {
            "instId": symbol,
            "ordId": ord_id
        }
        
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
            
        return await self._request("POST", endpoint, body)
    
    async def get_open_orders(self, symbol=''):
        """Получение активных ордеров"""
        endpoint = "/api/v5/trade/orders-pending"
        params = {"instId": symbol} if symbol else {}
        return await self._request("GET", endpoint, params=params)
    
    async def get_balance(self):
        """Получение баланса"""
        endpoint = "/api/v5/account/balance"
        return await self._request("GET", endpoint)
    
    async def get_instruments(self, inst_type='FUTURES'):
        """Получение списка инструментов"""
        endpoint = "/api/v5/public/instruments"
        params = {"instType": inst_type}
        return await self._request("GET", endpoint, params=params)
    

async def main():
    
    exchange = OKXExchange()
    # Размещение ордера
    order_result = await exchange.place_futures_limit_order(
        symbol="BTC-USDT-SWAP",
        side="buy",
        price=50000,
        size=0.001
    )
    print("Order placed:", order_result)

if __name__ == "__main__":
    asyncio.run(main())