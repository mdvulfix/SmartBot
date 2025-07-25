import os
import json
import logging
import asyncio
import signal
import threading
from logging.handlers import RotatingFileHandler
from exchange import OkxExchange
from bot import SmartBot



# Загрузка конфигурации
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



def print_banner():
    print("\n" + "="*50)
    print(" SmartBot v1 - Управление торговым ботом")
    print("="*50)
    print(" Доступные команды:")
    print(" - start: Запустить бота")
    print(" - stop: Остановить бота")
    print(" - status: Показать статус бота")
    print(" - exit: Выйти из программы")
    print("="*50 + "\n")

if __name__ == '__main__':
    print_banner()
    session = Session()
    session.run()