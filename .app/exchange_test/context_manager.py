import asyncio
from exchange_func_async_test import OKXExchange

async def main():
    async with OKXExchange() as exchange:
        # 1. Проверьте доступные инструменты
        instruments = await exchange.get_instruments('SWAP')
        print("Available instruments:", [inst['instId'] for inst in instruments['data'][:3]])
        
        # 2. Проверьте баланс
        balance = await exchange.get_balance()
        print("Balance:", balance)
        
        # 3. Попробуйте разместить минимальный ордер
        try:
            order_result = await exchange.place_futures_limit_order(
                symbol="BTC-USDT-SWAP",  # Убедитесь в правильности символа
                side="buy",
                price=30000,  # Используйте актуальную цену
                size=0.001    # Минимальный размер
            )
            print("Order placed:", order_result)
            
            # 4. Если ордер разместился - попробуйте его отменить
            if order_result['data'][0]['ordId']:
                await asyncio.sleep(1)  # Дайте время на обработку
                cancel_result = await exchange.cancel_order(
                    ord_id=order_result['data'][0]['ordId'],
                    symbol="BTC-USDT-SWAP"
                )
                print("Order canceled:", cancel_result)
                
        except Exception as e:
            print(f"Order placement failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())