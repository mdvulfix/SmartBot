import requests
import hashlib
import hmac
import base64
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode, quote

class OKXExchange:
    def __init__(self, config_path=None):
        """
        Инициализация подключения к демо-счету OKX
        
        :param config_path: Путь к файлу конфигурации (по умолчанию: okx_config.json в текущей директории)
        """
        if config_path is None:
            # Поиск файла конфигурации рядом со скриптом
            self.CONFIG_PATH = os.path.join(os.path.dirname(__file__), "okx_config.json")
        else:
            self.CONFIG_PATH = config_path
            
        if not os.path.exists(self.CONFIG_PATH):
            raise FileNotFoundError(f"Missing config file: {self.CONFIG_PATH}")
            
        self._load_config()
        self.BASE_URL = "https://www.okx.com"
        self.HEADER_SIMULATED_TRADING = "1"  # Флаг демо-счета
        
    def _load_config(self):
        """Загрузка конфигурации из JSON файла"""
        with open(self.CONFIG_PATH, "r") as f:
            config = json.load(f)
            
        self.api_key = config['api_key']
        self.secret_key = config['secret_key'].strip()
        self.passphrase = config['passphrase'].strip()
        
    def _sign(self, method, endpoint, body=None):
        now = datetime.now(timezone.utc)
        timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{now.microsecond // 1000:03d}Z"
        
        # Формирование сообщения для подписи
        if body:
            body_str = json.dumps(body, separators=(',', ':'))
            message = f"{timestamp}{method}{endpoint}{body_str}"
        else:
            message = f"{timestamp}{method}{endpoint}"
        
        # Создание подписи
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        # Формирование заголовков
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "x-simulated-trading": self.HEADER_SIMULATED_TRADING,
            "Content-Type": "application/json"
        }
        
        return headers, body_str if body else None
        
    def _request(self, method, endpoint, body=None, params=None):
        # Формируем полный путь для подписи (включая параметры для GET)
        full_endpoint = endpoint
        if method == "GET" and params:
            # Сортируем параметры по ключу и URL-кодируем
            sorted_params = sorted(params.items(), key=lambda x: x[0])
            encoded_params = urlencode(sorted_params, quote_via=quote)
            full_endpoint += "?" + encoded_params

        headers, body_str = self._sign(method, full_endpoint, body)
        url = self.BASE_URL + endpoint
        
        try:
            if method == "GET":
                # Для GET используем отсортированные параметры
                response = requests.get(
                    url, 
                    headers=headers, 
                    params=sorted_params if params else None
                )
            elif method == "POST":
                response = requests.post(url, headers=headers, data=body_str)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Проверка HTTP статуса
            response.raise_for_status()
            data = response.json()
            
            # Проверка кода ответа OKX (0 - успех)
            if data.get("code") != "0":
                raise Exception(f"API error: code={data.get('code')}, msg={data.get('msg')}")
            return data
            
        except requests.exceptions.RequestException as e:
            # Расширенная обработка ошибок
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('msg', 'Unknown error')
                    error_code = error_data.get('code', '')
                    raise Exception(f"Request failed (status {e.response.status_code}): [{error_code}] {error_msg}")
                except:
                    raise Exception(f"Request failed (status {e.response.status_code}): {e}")
            else:
                raise Exception(f"Request failed: {e}")
    
    # Публичные методы API
    
    def place_futures_limit_order(self, symbol, side, price, size, td_mode='cross', pos_side='net', cl_ord_id=''):
        """
        Размещает лимитный ордер на фьючерсном рынке
        
        :param symbol: ID инструмента (например 'BTC-USDT-SWAP')
        :param side: Направление сделки ('buy' или 'sell')
        :param price: Цена ордера
        :param size: Размер ордера
        :param td_mode: Режим маржи ('cross' или 'isolated')
        :param pos_side: Направление позиции ('long', 'short', 'net')
        :param cl_ord_id: Клиентский ID (опционально)
        :return: Ответ API
        """
        # Проверка типов данных
        if not isinstance(price, (int, float)) or not isinstance(size, (int, float)):
            raise TypeError("Price and size must be numeric types")
            
        endpoint = "/api/v5/trade/order"
        
        # Формируем тело запроса
        body = {
            "instId": symbol,
            "tdMode": td_mode,
            "side": side,
            "ordType": "limit",
            "px": str(price),
            "sz": str(size)
        }
        
        # Добавляем опциональные параметры
        if pos_side and pos_side != 'net':
            body["posSide"] = pos_side
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
            
        return self._request("POST", endpoint, body)
    
    def cancel_order(self, ord_id, symbol, cl_ord_id=''):
        """
        Отменяет активный ордер
        
        :param ord_id: ID ордера для отмены
        :param symbol: ID инструмента
        :param cl_ord_id: Клиентский ID (если был указан при размещении)
        :return: Ответ API
        """
        endpoint = "/api/v5/trade/cancel-order"
        
        # Формируем тело запроса
        body = {
            "instId": symbol,
            "ordId": ord_id
        }
        
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
            
        return self._request("POST", endpoint, body)
    
    def get_open_orders(self, symbol=''):
        """
        Получает список активных ордеров
        
        :param symbol: Фильтр по инструменту (опционально)
        :return: Ответ API
        """
        endpoint = "/api/v5/trade/orders-pending"
        params = {"instId": symbol} if symbol else {}
        return self._request("GET", endpoint, params=params)
    
    def get_balance(self):
        endpoint = "/api/v5/account/balance"
        return self._request("GET", endpoint)
    
    def get_instruments(self, inst_type='FUTURES'):
        """
        Получает список доступных инструментов
        
        :param inst_type: Тип инструмента (FUTURES, SPOT, SWAP)
        :return: Ответ API
        """
        endpoint = "/api/v5/public/instruments"
        params = {"instType": inst_type}
        return self._request("GET", endpoint, params=params)