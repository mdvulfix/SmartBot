import requests
import hashlib
import hmac
import base64
import json
import os
from datetime import datetime, timezone

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
    secret_key = config['secret_key'].strip()
    passphrase = config['passphrase'].strip()

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
    
    # Аутентификация
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{now.microsecond // 1000:03d}Z"
    
    # Ключевое исправление: формируем тело запроса для подписи
    body_str = json.dumps(body, separators=(',', ':'))
    
    # Формирование сообщения для подписи
    message = f"{timestamp}POST{ENDPOINT}{body_str}"
    print(f"Signing message: {message}")  # Для отладки
    
    # Альтернативная реализация подписи
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
    
    # Ключевое изменение: отправляем как строку JSON
    response = requests.post(
        url=BASE_URL + ENDPOINT,
        headers=headers,
        data=body_str  # Используем data вместо json
    )
    
    return response.json()

def get_open_orders(symbol: str):
    # Загрузка конфигурации
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "okx_config.json")
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    
    BASE_URL = "https://www.okx.com"
    ENDPOINT = "/api/v5/trade/orders-pending"
    HEADER_SIMULATED_TRADING = "1"
    
    # Параметры запроса
    params = {"instId": symbol}
    
    # Аутентификация
    now = datetime.now(timezone.utc)
    timestamp = now.strftime('%Y-%m-%dT%H:%M:%S') + f".{now.microsecond // 1000:03d}Z"
    message = f"{timestamp}GET{ENDPOINT}?instId={symbol}"
    
    signature = base64.b64encode(
        hmac.new(
            config['secret_key'].strip().encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    
    headers = {
        "OK-ACCESS-KEY": config['api_key'],
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": config['passphrase'].strip(),
        "x-simulated-trading": HEADER_SIMULATED_TRADING
    }
    
    response = requests.get(BASE_URL + ENDPOINT, headers=headers, params=params)
    return response.json()

# Пример использования с дополнительной диагностикой
if __name__ == "__main__":
    
    # Проверка перед отменой
    print("Open orders:", get_open_orders("BTC-USDT-SWAP"))
    print("Cancelling order...")
    cancel_result = cancel_futures_order_demo(
        ord_id="2728067338649313280",
        symbol="BTC-USDT-SWAP"
    )
    print("Cancel result:", cancel_result)
    