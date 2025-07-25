# === file: bot.py ===
import asyncio
import aiohttp
import hashlib
import hmac
import json
import os
import logging
import time
import websockets

from typing import Optional
from decimal import Decimal
from threading import Event

logger = logging.getLogger("SmartBot_v1")

class SmartBot:
    def __init__(self, exchange, symbol, grid_num, grid_step_pct, order_amount_usdt, leverage):
        self._exchange = exchange
        self._symbol = symbol
        self._grid_num = grid_num
        self._grid_step_pct = grid_step_pct
        self._order_amount_usdt = order_amount_usdt
        self._leverage = leverage
        
        # Состояние бота
        self._active_orders = []
        self._grid_levels = []
        self._reference_price = Decimal('0')
        self._running = False
        self._stop_event = Event()
        self._ws_task: Optional[asyncio.Task] = None
        self._main_task: Optional[asyncio.Task] = None

    async def get_current_price(self) -> Decimal:
        endpoint = f"/api/v5/market/ticker?instId={self._symbol}"
        res = await self._exchange.request_with_retry("GET", endpoint)
        if res['success']:
            return Decimal(res['data'][0]['last'])
        raise Exception("Failed to fetch current price")

    async def create_grid(self):
        self._grid_levels.clear()
        current_price = await self.get_current_price()
        step = Decimal(str(self._grid_step_pct)) / Decimal('100')
        
        for i in range(1, self._grid_num + 1):
            self._grid_levels.append({
                "price": current_price * (1 - step * i), 
                "side": "buy",
                "size": self.calculate_order_size(current_price)
            })
            self._grid_levels.append({
                "price": current_price * (1 + step * i),
                "side": "sell",
                "size": self.calculate_order_size(current_price)
            })
        logger.info(f"Created grid with {len(self._grid_levels)} levels")

    async def place_order(self, level) -> str:
        """Асинхронное размещение ордера"""
        logger.info(f"Placing {level['side']} order at {level['price']:.2f}")
        order_data = {
            "instId": self._symbol,
            "tdMode": "isolated",
            "side": level["side"],
            "ordType": "limit",
            "px": str(level["price"]),
            "sz": str(level["size"])
        }
        response = await self._exchange.request_with_retry("POST", "/api/v5/trade/order", order_data)
        return response['data'][0]['ordId']

    async def cancel_all_orders(self):
        """Отмена всех активных ордеров"""
        logger.info("Cancelling all active orders")
        await self._exchange.request_with_retry(
            "POST", 
            "/api/v5/trade/cancel-all-orders",
            {"instId": self._symbol}
        )
        self._active_orders.clear()

    async def refill_order(self, order_id: str):
        """Перевыставление ордера"""
        for info in self._active_orders:
            if info['id'] == order_id:
                level = info['level']
                logger.info(f"Re-filling order {order_id} at {level['price']}")
                try:
                    new_id = await self.place_order(level)
                    info['id'] = new_id
                    info['placed_time'] = time.time()
                except Exception as e:
                    logger.error(f"Failed to re-place order: {e}")
                return

    async def adjust_grid(self, new_price: Decimal):
        """Корректировка сетки при значительном изменении цены"""
        threshold = self._reference_price * (Decimal(self._grid_step_pct) / Decimal(100)) * 3
        if abs(new_price - self._reference_price) > threshold:
            logger.info(f"Price moved >{threshold:.2f}, adjusting grid")
            await self.create_grid()
            self._reference_price = new_price

    async def websocket_handler(self):
        """Обработчик WebSocket соединения"""
        uri = "wss://ws.okx.com:8443/ws/v5/private"
        async with websockets.connect(uri) as websocket:
            # Аутентификация
            timestamp = str(int(time.time()))
            sign = hmac.new(
                self._exchange.secret_key.encode(),
                f"{timestamp}GET/users/self/verify".encode(),
                hashlib.sha256
            ).hexdigest()
            
            auth_msg = {
                "op": "login",
                "args": [{
                    "apiKey": self._exchange.api_key,
                    "passphrase": self._exchange.passphrase,
                    "timestamp": timestamp,
                    "sign": sign
                }]
            }
            await websocket.send(json.dumps(auth_msg))
            
            # Подписка на ордера
            sub_msg = {
                "op": "subscribe",
                "args": [{"channel": "orders", "instType": "SWAP", "instId": self._symbol}]
            }
            await websocket.send(json.dumps(sub_msg))
            
            # Обработка сообщений
            while self._running:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30)
                    data = json.loads(message)
                    
                    if data.get('arg', {}).get('channel') == 'orders':
                        for order in data.get('data', []):
                            await self.process_order_update(order)
                            
                except asyncio.TimeoutError:
                    # Пинг для поддержания соединения
                    await websocket.send(json.dumps({"op": "ping"}))
                except Exception as e:
                    logger.error(f"WebSocket error: {e}")
                    break

    async def process_order_update(self, order_data):
        """Обработка обновления ордера"""
        order_id = order_data.get('ordId')
        state = order_data.get('state')
        
        if state == 'filled':
            self.send_telegram_alert(f"Order {order_id} filled")
            await self.refill_order(order_id)
        elif state in {'canceled', 'partial_filled'}:
            self._active_orders = [o for o in self._active_orders if o['id'] != order_id]
            logger.info(f"Order {order_id} removed (state: {state})")

    async def run(self):
        """Основной цикл работы бота"""
        if self._running:
            raise Exception("Bot is already running")
            
        self._running = True
        self._stop_event.clear()
        
        try:
            # Инициализация
            self._reference_price = await self.get_current_price()
            await self.create_grid()
            
            # Запуск WebSocket в отдельной задаче
            self._ws_task = asyncio.create_task(self.websocket_handler())
            
            # Основной цикл
            while self._running and not self._stop_event.is_set():
                try:
                    price = await self.get_current_price()
                    await self.adjust_grid(price)
                    await asyncio.sleep(30)  # Интервал проверки
                    
                except Exception as e:
                    logger.error(f"Main loop error: {e}")
                    await asyncio.sleep(5)
                    
        except asyncio.CancelledError:
            logger.info("Bot task cancelled")
        finally:
            await self.cleanup()
            self._running = False

    async def cleanup(self):
        """Очистка ресурсов"""
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except:
                pass

    async def start(self):
        """Запуск бота в фоновом режиме"""
        if self._running:
            raise Exception("Bot is already running")
            
        self._main_task = asyncio.create_task(self.run())
        return self._main_task
    
    async def stop(self, graceful: bool = True):
        """Остановка бота"""
        if not self._running:
            return
            
        logger.info("Stopping bot...")
        self._running = False
        self._stop_event.set()
        
        if graceful:
            try:
                await self.cancel_all_orders()
            except Exception as e:
                logger.error(f"Error during graceful stop: {e}")
        
        # Отмена задач
        if self._ws_task:
            self._ws_task.cancel()
        if self._main_task:
            self._main_task.cancel()
            
        logger.info("Bot stopped successfully")

    def send_telegram_alert(self, message: str):
        """Отправка уведомления в Telegram"""
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return
            
        async def send_async():
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    data = {"chat_id": chat_id, "text": message}
                    async with session.post(url, json=data) as resp:
                        if resp.status != 200:
                            logger.error(f"Telegram API error: {await resp.text()}")
            except Exception as e:
                logger.error(f"Telegram send error: {e}")
                
        asyncio.create_task(send_async())

    def calculate_order_size(self, price: Decimal) -> Decimal:
        return (Decimal(self._order_amount_usdt) / price).quantize(Decimal('0.00001'))