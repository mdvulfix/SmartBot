# === file: main.py ===

import asyncio
from decimal import Decimal, InvalidOperation

from exchange import OkxExchange

class Coin:
    def __init__(self, base: str, quote: str = "USDT", instrument_type: str = "SWAP"):
        self.base = base
        self.quote = quote
        self.instrument_type = instrument_type
    
    @property
    def instrument_id(self) -> str:
        if self.instrument_type == "SPOT":
            return f"{self.base}-{self.quote}"
        elif self.instrument_type == "SWAP":
            return f"{self.base}-{self.quote}-SWAP"
        else:
            return f"{self.base}-{self.quote}-{self.instrument_type}"

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
    "BTC": Coin("BTC", instrument_type="SWAP"),
    "ETH": Coin("ETH", instrument_type="SWAP"),
    "SOL": Coin("SOL", instrument_type="SWAP"),
    "XRP": Coin("XRP", instrument_type="SWAP")
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
                for name, coin in COINS.items():
                    print(f"  {name} ({coin.instrument_type}) → {coin.instrument_id}")
            
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
                try:
                    price = await exchange.get_symbol_price(coin.instrument_id)
                    print(f"Цена {coin.instrument_id}: {price}")
                except Exception as e:
                    print(f"❌ Ошибка получения цены: {e}")

            elif cmd == "order":
                if len(parts) < 5:
                    print("Использование: order SYMBOL SIDE PRICE [SIZE|AMOUNT]")
                    print("Пример: order BTC buy 50000 0.01   (размер)")
                    print("Или:    order BTC buy 50000 500    (сумма в USDT)")
                    continue
                
                symbol, side, price_s, size_s = parts[1:5]
                coin = COINS.get(symbol.upper())
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                    
                try:
                    price = Decimal(price_s)
                    size_or_amt = Decimal(size_s)
                except InvalidOperation:
                    print("❌ Некорректный формат PRICE или SIZE/AMOUNT")
                    continue
                
                # Определяем что передано: размер или сумма
                is_amount = len(parts) > 5 and parts[5].lower() == "amt"
                
                instrument_id = coin.instrument_id
                if is_amount:
                    order_id = await exchange.place_order(
                        instrument_id, 
                        side, 
                        price,
                        notional=size_or_amt
                    )
                else:
                    order_id = await exchange.place_order(
                        instrument_id, 
                        side, 
                        price,
                        size=size_or_amt
                    )
                    
                if order_id:
                    print(f"✅ Ордер размещён, ID={order_id}")
                else:
                    print("❌ Не удалось разместить ордер")

            elif cmd == "cancel":
                if len(parts) < 3:
                    print("Использование: cancel SYMBOL ORDER_ID")
                    continue
                symbol = parts[1].upper()
                order_id = parts[2]
                
                coin = COINS.get(symbol)
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                    
                ok = await exchange.cancel_order(coin.instrument_id, order_id)
                print("✅ Отменено" if ok else "❌ Не удалось отменить")

            elif cmd == "cancel_all":
                if len(parts) < 2:
                    print("Использование: cancel_all SYMBOL")
                    continue
                symbol = parts[1].upper()
                
                coin = COINS.get(symbol)
                if not coin:
                    print(f"❌ Монета {symbol} не поддерживается")
                    continue
                    
                canceled = await exchange.cancel_all_orders(coin.instrument_id)
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