import requests
import hashlib
import hmac
import base64
import json
import os
from datetime import datetime, timezone

class OKXDemoExchange:
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
        
    def _sign_request(self, method, endpoint, body=None):
        """
        Генерирует подпись и заголовки для запроса
        
        :param method: HTTP метод (GET, POST)
        :param endpoint: API эндпоинт
        :param body: Тело запроса (для POST)
        :return: Заголовки для запроса
        """
        # Генерация временной метки
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
        
    def _make_request(self, method, endpoint, body=None, params=None):
        """
        Выполняет запрос к API OKX
        
        :param method: HTTP метод
        :param endpoint: API эндпоинт
        :param body: Тело запроса (для POST)
        :param params: Параметры запроса (для GET)
        :return: Ответ API
        """
        headers, body_str = self._sign_request(method, endpoint, body)
        
        url = self.BASE_URL + endpoint
        
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, data=body_str)
        else:
            raise ValueError(f"Unsupported method: {method}")
            
        return response.json()
    
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
        endpoint = "/api/v5/trade/order"
        
        # Формируем тело запроса
        body = {
            "instId": symbol,
            "tdMode": td_mode,
            "side": side,
            "ordType": "limit",
            "px": str(price),
            "sz": str(size),
        }
        
        # Добавляем опциональные параметры
        if pos_side and pos_side != 'net':
            body["posSide"] = pos_side
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id
            
        return self._make_request("POST", endpoint, body)
    
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
            
        return self._make_request("POST", endpoint, body)
    
    def get_open_orders(self, symbol=''):
        """
        Получает список активных ордеров
        
        :param symbol: Фильтр по инструменту (опционально)
        :return: Ответ API
        """
        endpoint = "/api/v5/trade/orders-pending"
        params = {"instId": symbol} if symbol else {}
        return self._make_request("GET", endpoint, params=params)
    
    def get_balance(self):
        """
        Получает баланс демо-счета
        
        :return: Ответ API
        """
        endpoint = "/api/v5/account/balance"
        return self._make_request("GET", endpoint)
    
    def get_instruments(self, inst_type='FUTURES'):
        """
        Получает список доступных инструментов
        
        :param inst_type: Тип инструмента (FUTURES, SPOT, SWAP)
        :return: Ответ API
        """
        endpoint = "/api/v5/public/instruments"
        params = {"instType": inst_type}
        return self._make_request("GET", endpoint, params=params)

# Пример использования класса
if __name__ == "__main__":
    # Создаем экземпляр класса биржи
    exchange = OKXDemoExchange()
    
    # Пример: Получение баланса
    #balance = exchange.get_balance()
    #print("Balance:", balance)
    
    # Пример: Размещение ордера
    order_result = exchange.place_futures_limit_order(
        symbol="BTC-USDT-SWAP",
        side="buy",
        price=55000,
        size=1
    )
    print("Order placement result:", order_result)
    
    # Пример: Получение активных ордеров
    open_orders = exchange.get_open_orders("BTC-USDT-SWAP")
    print("Open orders:", open_orders)


    # Пример: Отмена ордера
    if order_result.get('code') == '0':
        ord_id = order_result['data'][0]['ordId']
        cancel_result = exchange.cancel_order(
            ord_id=ord_id,
            symbol="BTC-USDT-SWAP"
        )
        print("Cancel result:", cancel_result)

    # Пример: Отмена ордера
    #if order_result.get('code') == '0':
    #    ord_id = order_result['data'][0]['ordId']
    #cancel_result = exchange.cancel_order(
    #    ord_id="2731421038629457920",
    #    symbol="BTC-USDT-SWAP"
    #)
    #print("Cancel result:", cancel_result)