# === file: main.py ===

import asyncio
from decimal import Decimal, InvalidOperation

from exchange_v6 import OkxExchange
from coin_v1 import Coin

HELP_TEXT = """
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

# Определяем, с какими монетами работаем
COINS = {
    "BTC": Coin("BTC"),
    "ETH": Coin("ETH"),
    "SOL": Coin("SOL"),
    "XRP": Coin("XRP")
}

async def command_loop():
    # Передаём в конструктор список inst_id-ов
    symbols = [coin.instrument_id for coin in COINS.values()]
    exchange = OkxExchange(symbols)
    worker = None
    
    print("Интерактивный клиент OKX. Введите 'help' для списка команд.")

    while True:
        cmd_line = await asyncio.to_thread(input, "> ")
        parts = cmd_line.strip().split()
        if not parts:
            continue
        cmd = parts[0].lower()

        try:
            if cmd == "help":
                print(HELP_TEXT)

            elif cmd == "coins":
                print("Торгуемые монеты:")
                for coin in COINS.values():
                    print(f"  {coin.base}/{coin.quote}  →  {coin.instrument_id}")
            
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
                ccy = parts[1] if len(parts) > 1 else "USDT"
                bal = await exchange.get_balance(ccy)
                if bal is None:
                    print(f"❌ Не удалось получить баланс {ccy}")
                else:
                    print(f"💰 Баланс {ccy}: {bal}")

            elif cmd == "price":
                if len(parts) < 2:
                    print("❌ Укажите монету, например: price BTC")
                    continue
                base = parts[1].upper()
                coin = COINS.get(base)
                if not coin:
                    print(f"❌ Монета {base} не поддерживается")
                    continue
                instrument_id = coin.instrument_id
                try:
                    price = await exchange.get_symbol_price(instrument_id)
                    print(f"Цена {instrument_id}: {price}")
                except Exception as e:
                    print(f"❌ Ошибка получения цены: {e}")

            elif cmd == "order":
                if len(parts) != 5:
                    print("Использование: order SYMBOL SIDE PRICE SIZE")
                    continue
                symbol, side, price_s, size_s = parts[1:]
                coin = COINS.get(symbol.upper())
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                try:
                    price = Decimal(price_s)
                    size = Decimal(size_s)
                except InvalidOperation:
                    print("❌ Некорректный формат PRICE или SIZE")
                    continue
                instrument_id = coin.instrument_id
                order_id = await exchange.place_order(instrument_id, side, price, size)
                if order_id:
                    print(f"✅ Ордер размещён, ID={order_id}")
                else:
                    print("❌ Не удалось разместить ордер")

            elif cmd == "cancel":
                if len(parts) != 3:
                    print("Использование: cancel SYMBOL ORDER_ID")
                    continue
                symbol, order_id = parts[1], parts[2]
                ok = await exchange.cancel_order(symbol, order_id)
                print("✅ Отменено" if ok else "❌ Не удалось отменить")

            elif cmd == "cancel_all":
                if len(parts) != 2:
                    print("Использование: cancel_all SYMBOL")
                    continue
                symbol = parts[1]
                canceled = await exchange.cancel_all_orders(symbol)
                print(f"✅ Отменены ордера: {canceled}" if canceled else "❌ Нет отменённых ордеров")

            elif cmd == "status":
                report = await exchange.get_status_report()
                print("📝 Статус биржи:")
                for k, v in report.items():
                    print(f"  {k}: {v}")

            elif cmd == "quit":
                if worker and not worker.done():
                    print("⏳ Останавливаю перед выходом...")
                    await exchange.stop()
                print("👋 До встречи!")
                break

            else:
                print(f"❓ Неизвестная команда: {cmd}. Введите 'help'.")

        except Exception as e:
            print(f"Внутренняя ошибка команды '{cmd}': {e}")

if __name__ == "__main__":
    asyncio.run(command_loop())
