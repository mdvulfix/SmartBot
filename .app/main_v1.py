# === file: main.py ===
import os, json, asyncio

from decimal import Decimal, InvalidOperation
from exchange import OkxExchange
from coin import Coin


# Определяем, с какими монетами работаем
COINS = {
    "USDT": Coin("USDT"),
    "BTC": Coin("BTC"),
    "ETH": Coin("ETH"),
    "SOL": Coin("SOL"),
    "XRP": Coin("XRP")
}

async def command_loop():
    config_path = os.path.join(os.path.dirname(__file__), "okx_config.json")
    if not os.path.exists(config_path):
        #self._logger.error(f"Missing config file: {config_path}")
        raise FileNotFoundError(config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    exchange = OkxExchange(config = config, demo = True)
    worker = None
    
    print("Интерактивный клиент OKX. Введите 'help' для списка команд.")

    while True:
        cmd_line = await asyncio.to_thread(input, "> ")
        parts = cmd_line.strip().split()
        if not parts:
            continue
        cmd = parts[0].lower()

        try:
            if   cmd == "help":
                help_text = """
                    Доступные команды:
                    coins --> Показать поддерживаемые символы и их id.
                    start --> Запустить health-loop.
                    stop --> Остановить health-loop.
                    balance --> Показать баланс валюты.
                    price --> Показать цену SYMBOL.
                    order --> Разместить лимит‑ордер.
                    cancel --> Отменить ордер.
                    cancel_all --> Отменить все ордера по SYMBOL.
                    status --> Отчёт по состоянию биржи.
                    help --> Список доступных команд.
                    quit --> Выход.
                """
                print(help_text)

            elif cmd == "coins":
                print("Торгуемые монеты:")
                for coin in COINS.values():
                    print(f"  {coin.symbol_id}")
            
            elif cmd == "start":
                if worker and not worker.done():
                    print("❗ Run loop уже запущен")
                    continue
                await exchange.run()
                worker = exchange._run_task
                print("✅ Run loop запущен")

            elif cmd == "stop":
                if not worker or worker.done():
                    print("❗ Run loop не запущен")
                    continue
                print("⏳ Останавливаю run loop...")
                await exchange.stop()
                print("✅ Run loop остановлен")

            elif cmd == "balance":
                inpt_symbol = parts[1] if len(parts) > 1 else "USDT"
                symbol = inpt_symbol.upper()
                
                coin = COINS.get(symbol)
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                try:
                    balance = await exchange.get_balance(coin)
                    if balance is None:
                        print(f"❌ Не удалось получить баланс {symbol}")
                    else:
                        print(f"💰 Баланс {symbol}: {balance}")

                except Exception as e:
                    print(f"❌ Ошибка получения баланса: {e}")
                
            elif cmd == "price":
                if len(parts) < 2:
                    print("❌ Укажите монету, например: price BTC")
                    continue
                inpt_symbol = parts[1]
                symbol = inpt_symbol.upper()
                coin = COINS.get(symbol)
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                try:
                    price = await exchange.get_symbol_price(coin)
                    print(f"Цена {symbol}: {price}")
                except Exception as e:
                    print(f"❌ Ошибка получения цены: {e}")
                
            elif cmd == "place_limit_order_by_size":
                if len(parts) != 5:
                    print("Использование: place_order SYMBOL SIDE PRICE SIZE")
                    print("Пример: order BTC buy 50000 0.01 (размер)")
                    continue
                
                inpt_symbol, inpt_side, inpt_price, inpt_size = parts[1:]
                symbol = inpt_symbol.upper()
                coin = COINS.get(symbol)
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                try:
                    price = Decimal(inpt_price)
                    size = Decimal(inpt_size)
                except InvalidOperation:
                    print("❌ Некорректный формат PRICE или SIZE")
                    continue
                
                side = inpt_side.lower()
                order_id = await exchange.place_limit_order_by_size(coin, side, price, size)
                
                if order_id:
                    print(f"✅ Ордер размещён, ID: {order_id}")
                else:
                    print("❌ Не удалось разместить ордер")

            elif cmd == "place_limit_order_by_amount":
                if len(parts) != 5:
                    print("Использование: place_order SYMBOL SIDE PRICE AMOUNT")
                    print("Пример: order BTC buy 50000 500 (сумма в USDT)")
                    continue
            
                inpt_symbol, inpt_side, inpt_price, inpt_amount = parts[1:]
                symbol = inpt_symbol.upper()
                coin = COINS.get(symbol)
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                try:
                    price = Decimal(inpt_price)
                    amount = Decimal(inpt_amount)
                except InvalidOperation:
                    print("❌ Некорректный формат PRICE или AMOUNT")
                    continue
                
                side = inpt_side.lower()
                order_id = await exchange.place_limit_order_by_amount(coin, side, price, amount)
                
                if order_id:
                    print(f"✅ Ордер размещён, ID: {order_id}")
                else:
                    print("❌ Не удалось разместить ордер")
                
            elif cmd == "cancel_order":
                if len(parts) < 3:
                    print("Использование: cancel SYMBOL ORDER_ID")
                    continue
                symbol = parts[1].upper()
                order_id = parts[2]
                
                coin = COINS.get(symbol)
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                    
                ok = await exchange.cancel_order(coin, order_id)
                print("✅ Отменено" if ok else "❌ Не удалось отменить")

            elif cmd == "cancel_all_orders":
                if len(parts) < 2:
                    print("Использование: cancel_all_orders SYMBOL")
                    continue
                symbol = parts[1].upper()
                
                coin = COINS.get(symbol)
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                    
                canceled = await exchange.cancel_all_orders(coin)
                if canceled:
                    print(f"✅ Отменены ордера: {', '.join(canceled)}")
                else:
                    print("❌ Нет активных ордеров для отмены")

            elif cmd == "status":
                report = await exchange.get_status_report()
                print("📝 Статус биржи:")
                print(f"  Состояние: {report['state']}")
                print(f"  Последнее обновление: {report['last_update']}")
                print(f"  Баланс USDT: {report['balance']}")
                print(f"  Операционный: {'Да' if report['is_operational'] else 'Нет'}")
                print(f"  Требует внимания: {'Да' if report['needs_attention'] else 'Нет'}")
                print("  История состояний:")
                for state in report['state_history']:
                    print(f"    - {state['timestamp']}: {state['from']} → {state['to']}")

            elif cmd == "quit":
                if worker and not worker.done():
                    print("⏳ Останавливаю перед выходом...")
                    await exchange.stop()
                    # Дать время на завершение операций
                    await asyncio.sleep(0.5)
                
                # Явно закрыть соединение
                await exchange.close()
                print("👋 До встречи!")
                break

            else:
                print(f"❓ Неизвестная команда: {cmd}. Введите 'help'.")

        except Exception as e:
            print(f"Внутренняя ошибка команды '{cmd}': {e}")

if __name__ == "__main__":
    asyncio.run(command_loop())