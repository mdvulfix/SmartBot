import requests
import time
import hashlib
import hmac
import base64
import json
import os
from datetime import datetime, timezone

def place_futures_limit_order_demo(
        symbol: str,           # e.g. 'BTC-USD-240329' или 'BTC-USDT-SWAP'
        side: str,              # 'buy' или 'sell'
        price: float,           # Цена ордера
        size: int,              # Размер контракта
        td_mode: str = 'cross', # 'cross' или 'isolated'
        pos_side: str = 'net',  # 'long', 'short', 'net'
        cl_ord_id: str = '',    # Клиентский ID (опционально)
    ) -> dict:
    
    # Загрузка конфигурации из JSON
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "okx_config.json")
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    api_key = config['api_key']
    secret_key = config['secret_key']
    passphrase = config['passphrase']

    # Настройки демо-режима
    BASE_URL = "https://www.okx.com"
    ENDPOINT = "/api/v5/trade/order"
    HEADER_SIMULATED_TRADING = "1"  # Флаг демо-счета
    
    # Формируем тело запроса
    body = {
        "instId": symbol,
        "tdMode": td_mode,
        "side": side,
        "ordType": "limit",
        "px": str(price),
        "sz": str(size),
    }
    
    # Добавляем posSide только если указано значение отличное от 'net'
    if pos_side and pos_side != 'net':
        body["posSide"] = pos_side
    
    if cl_ord_id:
        body["clOrdId"] = cl_ord_id
    
    # Аутентификация
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{int(now.microsecond / 1000):03d}Z"
    
    message = timestamp + 'POST' + ENDPOINT + json.dumps(body)
    signature = base64.b64encode(
        hmac.new(
            secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    
    # Заголовки запроса
    headers = {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "x-simulated-trading": HEADER_SIMULATED_TRADING,
        "Content-Type": "application/json"
    }
    
    print("Request Body:", json.dumps(body, indent=2))
    print("Headers:", headers)

    # Отправка запроса
    response = requests.post(
        url=BASE_URL + ENDPOINT,
        headers=headers,
        json=body
    )
    
    return response.json()

def cancel_futures_order_demo(
        ord_id: str,            # ID ордера для отмены
        symbol: str,             # ID инструмента
        cl_ord_id: str = '',    # Клиентский ID (опционально)
    ) -> dict:
    
    # Загрузка конфигурации из JSON
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "okx_config.json")
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    api_key = config['api_key']
    secret_key = config['secret_key']
    passphrase = config['passphrase']

    # Настройки демо-режима
    BASE_URL = "https://www.okx.com"
    ENDPOINT = "/api/v5/trade/cancel-order"
    HEADER_SIMULATED_TRADING = "1"  # Флаг демо-счета
    
    # Формируем тело запроса
    body = {
        "instId": symbol,
        "ordId": ord_id
    }
    
    if cl_ord_id:
        body["clOrdId"] = cl_ord_id
    
    # Аутентификация (с исправлением)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{int(now.microsecond / 1000):03d}Z"
    
    # Критическое исправление: правильное формирование message
    message = timestamp + 'POST' + ENDPOINT + json.dumps(body, separators=(',', ':'))
    
    # Создаем подпись
    signature = base64.b64encode(
        hmac.new(
            secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    
    # Заголовки запроса
    headers = {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "x-simulated-trading": HEADER_SIMULATED_TRADING,
        "Content-Type": "application/json"
    }
    
    print(f"Timestamp: {timestamp}")
    print(f"Message: {message}")
    print(f"Signature: {signature}")
    print(f"Headers: {headers}")
    print(f"Body: {body}")

    # Отправка запроса
    response = requests.post(
        url=BASE_URL + ENDPOINT,
        headers=headers,
        json=body
    )
    
    return response.json()

if __name__ == "__main__":
    # Пример вызова с КОРРЕКТНЫМ символом
    result = place_futures_limit_order_demo(
         symbol="BTC-USDT-SWAP",  # Исправленный символ для перпетуального контракта
         side="buy",              # Покупка
         price=55500.0,           # Цена в USDT
         size=1,                  # 1 контракт
         td_mode="cross",         # Кросс-маржинальный режим
         # pos_side не передаем (по умолчанию 'net')
    )

    print(result)
