import time
import hmac
import base64
import hashlib
import httpx
import json
import asyncio
from pathlib import Path

CONFIG_PATH = Path("okx_config.json")
BASE_URL = "https://www.okx.com"

def load_okx_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Файл конфигурации {CONFIG_PATH} не найден.")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def place_demo_limit_order(price="50000", notional="100"):
    config = load_okx_config()

    api_key = config["api_key"]
    secret_key = config["secret_key"]
    passphrase = config["passphrase"]
    is_demo = config.get("demo", False)

    endpoint = "/api/v5/trade/order"
    url = BASE_URL + endpoint

    order_data = {
        "instId": "BTC-USDT-SWAP",
        "tdMode": "cross",
        "side": "buy",
        "ordType": "limit",
        "px": price,
        "notional": notional,
        "ccy": "USDT"
    }

    timestamp = str(time.time())
    body = json.dumps(order_data)
    message = timestamp + 'POST' + endpoint + body
    signature = base64.b64encode(
        hmac.new(
            secret_key.encode(),
            message.encode(),
            digestmod=hashlib.sha256
        ).digest()
    ).decode()

    headers = {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": signature,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
    }

    if is_demo:
        headers["x-simulated-trading"] = "1"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, data=body)
        return response.json()

async def main():
    result = await place_demo_limit_order(price="50000", notional="100")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
