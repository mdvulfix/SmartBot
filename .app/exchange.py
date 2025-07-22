# === file: exchange.py ===
import time
import hmac
import hashlib
import base64
import requests
import json
import logging
from decimal import Decimal

logger = logging.getLogger("SmartBot_v1")

class OkxExchange:
    def __init__(self, api_key, secret_key, passphrase, demo=False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = "https://www.okx.com"
        self.demo = demo

    def sign(self, timestamp, method, request_path, body):
        message = f"{timestamp}{method}{request_path}{body}"
        mac = hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def get_headers(self, method, path, body=""):
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
        signature = self.sign(timestamp, method, path, body)
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }
        if self.demo:
            headers["x-simulated-trading"] = "1"
        return headers

    def request_with_retry(self, method, path, payload=None):
        for _ in range(3):
            try:
                body = json.dumps(payload) if payload else ""
                headers = self.get_headers(method, path, body)
                url = self.base_url + path
                response = requests.request(method, url, headers=headers, data=body)
                data = response.json()
                if response.ok:
                    return {"success": True, "data": data.get("data", [])}
                else:
                    logger.error(f"Request failed: {data}")
            except Exception as e:
                logger.exception(f"Request error: {e}")
            time.sleep(1)
        return {"success": False, "data": []}

    def get_balance(self, ccy="USDT"):
        endpoint = "/api/v5/account/balance"
        res = self.request_with_retry("GET", endpoint)
        if res['success']:
            for acc in res['data'][0]['details']:
                if acc['ccy'] == ccy:
                    bal = Decimal(acc['availBal'])
                    logger.info(f"Available {ccy}: {bal}")
                    return bal
        logger.error("Failed to fetch balance")
        return Decimal('0')