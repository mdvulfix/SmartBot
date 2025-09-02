####################
### main.py
####################

"""Точка входа и интерактивный CLI"""
import os
import json
import asyncio
from decimal import Decimal, getcontext

from models.coin import Coin
from strategies.grid_strategy import GridStrategy
from execution.order_manager import OrderManager
from execution.position_manager import PositionManager
from core.bot import Bot
from core.exchange import OkxExchange

# Настройки Decimal (точность и избегаем двусмысленностей)
getcontext().prec = 28

# Поддерживаемые монеты
COINS = {
    "USDT": Coin("USDT"),
    "BTC": Coin("BTC"),
    "ETH": Coin("ETH"),
    "SOL": Coin("SOL"),
    "XRP": Coin("XRP")
}

async def command_loop():
    """Интерактивный интерфейс управления"""
    # Загрузка конфигурации
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}")
        print("Create config.json with fields: api_key, secret_key, passphrase")
        return

    with open(config_path, "r") as f:
        config = json.load(f)

    exchange = OkxExchange(config, demo=True)
    bots = {}  # Активные торговые боты

    print("OKX Trading Bot CLI. Type 'help' for commands.")

    while True:
        try:
            cmd_line = await asyncio.to_thread(input, "> ")
            parts = cmd_line.strip().split()
            if not parts:
                continue

            cmd = parts[0].lower()

            if cmd == "help":
                print_help()
            elif cmd == "coins":
                print(", ".join(COINS.keys()))
            elif cmd == "start":
                await exchange.run()
                print("Exchange monitoring started")
            elif cmd == "stop":
                await exchange.stop()
                print("Exchange monitoring stopped")
            elif cmd == "balance":
                await handle_balance(exchange, parts)
            elif cmd == "price":
                await handle_price(exchange, parts)
            elif cmd == "order":
                await handle_order(exchange, parts)
            elif cmd == "cancel":
                await handle_cancel(exchange, parts)
            elif cmd == "cancel_all":
                await handle_cancel_all(exchange, parts)
            elif cmd == "status":
                await handle_status(exchange)
            elif cmd == "init_bot":
                await handle_init_bot(exchange, bots, parts)
            elif cmd == "start_bot":
                await handle_start_bot(bots, parts)
            elif cmd == "stop_bot":
                await handle_stop_bot(bots, parts)
            elif cmd == "bot_status":
                await handle_bot_status(bots, parts)
            elif cmd == "quit":
                await handle_quit(exchange, bots)
                break
            else:
                print(f"Unknown command: {cmd}")

        except Exception as e:
            print(f"Error: {e}")

def print_help():
    """Вывод списка команд"""
    print("""
    Available commands:
      coins             - List supported coins
      start             - Start exchange monitoring
      stop              - Stop exchange monitoring
      balance [COIN]    - Get balance (default: USDT)
      price COIN        - Get current price
      order COIN SIDE PRICE SIZE - Place limit order
      cancel COIN ORDER_ID - Cancel order
      cancel_all COIN   - Cancel all orders for coin
      status            - Exchange status report
      init_bot COIN LOWER UPPER LEVELS SIZE - Initialize grid bot
      start_bot COIN    - Start trading bot
      stop_bot COIN     - Stop trading bot
      bot_status COIN   - Bot performance report
      quit              - Exit program
    """)

async def handle_balance(exchange, parts):
    """Обработка запроса баланса"""
    symbol = parts[1].upper() if len(parts) > 1 else "USDT"
    coin = COINS.get(symbol)
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return

    balance = await exchange.get_balance(coin)
    if balance is None:
        print("Failed to get balance")
    else:
        print(f"{symbol} balance: {balance}")

async def handle_price(exchange, parts):
    """Обработка запроса цены"""
    if len(parts) < 2:
        print("Specify coin: price BTC")
        return

    symbol = parts[1].upper()
    coin = COINS.get(symbol)
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return

    price = await exchange.get_symbol_price(coin)
    print(f"{symbol} price: {price}")

async def handle_order(exchange, parts):
    """Обработка размещения ордера"""
    if len(parts) < 5:
        print("Usage: order COIN SIDE PRICE SIZE")
        return

    symbol, side, price_str, size_str = parts[1:5]
    coin = COINS.get(symbol.upper())
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return

    try:
        price = Decimal(price_str)
        size = Decimal(size_str)
    except Exception:
        print("Invalid price or size")
        return

    order_id = await exchange.place_limit_order(coin, side, price, size)
    if order_id:
        print(f"Order placed: {order_id}")
    else:
        print("Failed to place order")

async def handle_cancel(exchange, parts):
    """Обработка отмены ордера"""
    if len(parts) < 3:
        print("Usage: cancel COIN ORDER_ID")
        return

    symbol, order_id = parts[1:3]
    coin = COINS.get(symbol.upper())
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return

    success = await exchange.cancel_order(coin, order_id)
    print("Order canceled" if success else "Failed to cancel")

async def handle_cancel_all(exchange, parts):
    """Обработка отмены всех ордеров"""
    if len(parts) < 2:
        print("Usage: cancel_all COIN")
        return

    symbol = parts[1].upper()
    coin = COINS.get(symbol)
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return

    canceled = await exchange.cancel_all_orders(coin)
    if canceled:
        print(f"Canceled orders: {', '.join(canceled)}")
    else:
        print("No orders to cancel")

async def handle_status(exchange):
    """Вывод состояния биржи"""
    status = await exchange.get_status_report()
    print(f"State: {status['state']}")
    print(f"Balance: {status['balance']} USDT")
    print(f"Operational: {'Yes' if status['operational'] else 'No'}")
    print(f"Needs attention: {'Yes' if status['needs_attention'] else 'No'}")

async def handle_init_bot(exchange, bots, parts):
    """Инициализация торгового бота"""
    if len(parts) < 6:
        print("Usage: init_bot COIN LOWER UPPER LEVELS SIZE")
        return

    symbol, lower_str, upper_str, levels_str, size_str = parts[1:6]
    coin = COINS.get(symbol.upper())
    if not coin:
        print(f"Unsupported coin: {symbol}")
        return

    try:
        lower = Decimal(lower_str)
        upper = Decimal(upper_str)
        levels = int(levels_str)
        size = Decimal(size_str)
    except Exception:
        print("Invalid parameters")
        return

    try:
        strategy = GridStrategy(coin, lower, upper, levels, size)
    except Exception as e:
        print(f"Strategy init error: {e}")
        return

    order_manager = OrderManager()
    position_manager = PositionManager()

    bot = Bot(exchange, strategy, order_manager, position_manager)
    bots[symbol.upper()] = bot
    print(f"Bot initialized for {symbol.upper()}")

async def handle_start_bot(bots, parts):
    """Запуск торгового бота"""
    if len(parts) < 2:
        print("Usage: start_bot COIN")
        return

    symbol = parts[1].upper()
    bot = bots.get(symbol)
    if not bot:
        print(f"No bot for {symbol}")
        return

    await bot.start()
    print(f"Bot started for {symbol}")

async def handle_stop_bot(bots, parts):
    """Остановка торгового бота"""
    if len(parts) < 2:
        print("Usage: stop_bot COIN")
        return

    symbol = parts[1].upper()
    bot = bots.get(symbol)
    if not bot:
        print(f"No bot for {symbol}")
        return

    await bot.stop()
    print(f"Bot stopped for {symbol}")

async def handle_bot_status(bots, parts):
    """Отчет о работе бота"""
    if len(parts) < 2:
        print("Usage: bot_status COIN")
        return

    symbol = parts[1].upper()
    bot = bots.get(symbol)
    if not bot:
        print(f"No bot for {symbol}")
        return

    report = bot.get_performance_report()
    print(f"Strategy: {report['strategy']}")
    print(f"Coin: {report['coin']}")
    orders = report.get('orders', {})
    positions = report.get('positions', {})
    print(f"Orders: {orders.get('total_orders', 0)} | Win rate: {orders.get('win_rate', 0):.2%} | Profit: {orders.get('total_profit', '0')}")
    print(f"Positions: {positions.get('total_positions', 0)} | Win rate: {positions.get('win_rate', 0):.2%} | Profit: {positions.get('total_profit', '0')}")
    if report['current_position']:
        cp = report['current_position']
        print(f"Current position: Size={cp['size']} | PnL={cp['realized_pnl']} | Unrealized={cp['unrealized_pnl']}")

async def handle_quit(exchange, bots):
    """Корректное завершение работы"""
    print("Stopping bots...")
    for bot in list(bots.values()):
        await bot.stop()

    print("Stopping exchange...")
    await exchange.stop()
    await exchange.close()

    print("Goodbye!")

if __name__ == "__main__":
    asyncio.run(command_loop())
