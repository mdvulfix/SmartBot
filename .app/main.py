import os
import json
import logging
from logging.handlers import RotatingFileHandler
from exchange import OkxExchange
from bot import SmartBot

# Настройка логирования
logger = logging.getLogger("SmartBot_v1")
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

file_handler = RotatingFileHandler("SmartBot_v1.log", maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Загрузка конфигурации из JSON
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "okx_config.json")
if not os.path.exists(CONFIG_PATH):
    logger.error(f"Конфигурационный файл не найден: {CONFIG_PATH}")
    raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

API_KEY = config.get("api_key")
SECRET_KEY = config.get("secret_key")
PASSPHRASE = config.get("passphrase")
SYMBOL = config.get("symbol", "BTC-USDT-SWAP")
GRID_NUM = config.get("grid_num", 5)
GRID_STEP_PCT = config.get("grid_step_pct", 1.0)
ORDER_AMOUNT_USDT = config.get("order_amount_usdt", 10)
LEVERAGE = config.get("leverage", 10)
DEMO_MODE = config.get("demo", True)

# Запуск бота
if __name__ == '__main__':
    exchange = OkxExchange(API_KEY, SECRET_KEY, PASSPHRASE, demo=DEMO_MODE)
    bot = SmartBot(exchange, SYMBOL, GRID_NUM, GRID_STEP_PCT, ORDER_AMOUNT_USDT, LEVERAGE)
    bot.run()
    
