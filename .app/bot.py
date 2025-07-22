# === file: bot.py ===
import time
import json
import os
import logging
import websocket
from decimal import Decimal
from threading import Thread
import requests
from exchange import OkxExchange

logger = logging.getLogger("SmartBot_v1")

class SmartBot:
    def __init__(self, client, symbol, grid_num, grid_step_pct, order_amount_usdt, leverage):
        self.client = client
        self.symbol = symbol
        self.grid_num = grid_num
        self.grid_step_pct = grid_step_pct
        self.order_amount_usdt = order_amount_usdt
        self.leverage = leverage
        self.active_orders = []
        self.grid_levels = []
        self.reference_price = Decimal('0')

    def get_current_price(self):
        endpoint = f"/api/v5/market/ticker?instId={self.symbol}"
        res = self.client.request_with_retry("GET", endpoint)
        if res['success']:
            return Decimal(res['data'][0]['last'])
        raise Exception("Failed to fetch current price")

    def create_grid(self):
        self.grid_levels.clear()
        current_price = self.get_current_price()
        step = Decimal(str(self.grid_step_pct)) / Decimal('100')
        for i in range(1, self.grid_num + 1):
            self.grid_levels.append({"price": current_price * (1 - step * i), "side": "buy"})
            self.grid_levels.append({"price": current_price * (1 + step * i), "side": "sell"})
        logger.info(f"Created grid with {len(self.grid_levels)} levels.")

    def place_order(self, level):
        # Псевдореализация
        logger.info(f"Placing order at {level['price']:.2f} for {level['side']}")
        return str(int(time.time() * 1000))

    def refill_order(self, order_id):
        for info in self.active_orders:
            if info['id'] == order_id:
                level = info['level']
                logger.info(f"Re-filling order {order_id} at {level['price']}")
                new_id = self.place_order(level)
                if new_id:
                    info['id'] = new_id
                    info['placed_time'] = time.time()
                else:
                    logger.warning(f"Failed to re-place order for level {level['price']}, keeping old ID")
                return

    def adjust_grid(self, new_price):
        threshold = self.grid_levels[0]['price'] * Decimal('0.05')
        if abs(new_price - self.reference_price) > threshold:
            logger.info("Price moved significantly, adjusting grid")
            old_reference = self.reference_price
            self.create_grid()
            self.reference_price = new_price
            logger.info(f"Grid adjusted. Reference price updated from {old_reference} to {new_price}")

    def send_telegram_alert(self, message):
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message}
        try:
            requests.post(url, json=data, timeout=5)
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")

    def on_ws_message(self, ws, message):
        data = json.loads(message)
        if data.get('arg', {}).get('channel') == 'orders':
            for order in data.get('data', []):
                order_id = order.get('ordId')
                state = order.get('state')

                if state == 'filled':
                    self.send_telegram_alert(f"Order {order_id} filled")
                    self.refill_order(order_id)
                elif state in {'canceled', 'partial_filled'}:
                    self.active_orders = [o for o in self.active_orders if o['id'] != order_id]
                    logger.info(f"Order {order_id} removed from active_orders due to state '{state}'")

    def start_ws(self):
        ws_url = 'wss://ws.okx.com:8443/ws/v5/private'
        ws = websocket.WebSocketApp(ws_url, on_message=self.on_ws_message)
        Thread(target=ws.run_forever, daemon=True).start()

    def watchdog(self):
        self.last_heartbeat = time.time()
        def monitor():
            while True:
                time.sleep(60)
                if time.time() - self.last_heartbeat > 120:
                    logger.critical("Watchdog detected no activity for 2 minutes. Exiting.")
                    self.send_telegram_alert("Bot has stopped responding. Restart required.")
                    os._exit(1)
        Thread(target=monitor, daemon=True).start()

    def run(self, interval=30):
        logger.info("Starting bot")
        self.watchdog()
        self.start_ws()
        self.reference_price = self.get_current_price()
        self.create_grid()
        while True:
            try:
                price = self.get_current_price()
                self.last_heartbeat = time.time()
                self.client.get_balance()
                self.adjust_grid(price)
                time.sleep(interval)
            except KeyboardInterrupt:
                break
            except Exception:
                logger.exception("Error in main loop")