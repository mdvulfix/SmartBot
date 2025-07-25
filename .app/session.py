import asyncio
import signal
import threading

from logging import Logger
from exchange import OkxExchange
from bot import SmartBot

class Session():
    def __init__(self, api_key, secret_key, passphrase, mode):
        self._logger = Logger()
        self._exchange = OkxExchange(api_key, secret_key, passphrase, mode)
        self._bot = SmartBot(self._exchange)
        self._stop_event = threading.Event()
        self._command_thread = None
        self._bot_task = None


    def console(self):
        """Прослушивание команд из терминала"""
        while not self._stop_event.is_set():
            try:
                cmd = input("Введите команду (start/stop/status/exit): ").strip().lower()
                
                if cmd == "start":
                    asyncio.run_coroutine_threadsafe(self.start_bot(), asyncio.get_event_loop())
                elif cmd == "stop":
                    asyncio.run_coroutine_threadsafe(self.stop_bot(), asyncio.get_event_loop())
                elif cmd == "status":
                    status = "работает" if self._bot_task and not self._bot_task.done() else "остановлен"
                    print(f"Текущий статус бота: {status}")
                elif cmd == "exit":
                    self.shutdown()
                    break
                else:
                    print("Неизвестная команда. Доступные команды: start, stop, status, exit")
            except Exception as e:
                self._logger.manager().error(f"Ошибка обработки команды: {e}")

    def shutdown(self):
        """Корректное завершение работы"""
        self._stop_event.set()
        if self._command_thread:
            self._command_thread.join(timeout=1)
        
        if self._bot_task and not self._bot_task.done():
            asyncio.run_coroutine_threadsafe(self.stop_bot(), asyncio.get_event_loop())

    def run(self):
        """Основной метод запуска"""
        # Обработка сигналов для корректного завершения
        signal.signal(signal.SIGINT, lambda s, f: self.shutdown())
        signal.signal(signal.SIGTERM, lambda s, f: self.shutdown())

        # Запуск потока для обработки команд
        self._command_thread = threading.Thread(target=self.command_listener, daemon=True)
        self._command_thread.start()

        # Запуск основного цикла asyncio
        loop = asyncio.get_event_loop()
        try:
            loop.run_forever()
        finally:
            self.shutdown()
            loop.close()

    async def start_bot(self):
        """Запуск бота в асинхронном режиме"""
        if self._bot_task and not self._bot_task.done():
            self._logger.manager().warning("Бот уже запущен")
            return

        self._logger.manager().info("Запуск бота...")
        self._bot_task = asyncio.create_task(self._bot.run())
        try:
            await self._bot_task
        except asyncio.CancelledError:
            self._logger.manager().info("Работа бота была остановлена")

    async def stop_bot(self, graceful=True):
        """Остановка бота"""
        if not self._bot_task or self._bot_task.done():
            self._logger.manager().warning("Бот не запущен")
            return

        self._logger.manager().info("Остановка бота...")
        await self._bot.stop(graceful=graceful)
        self._bot_task.cancel()
        try:
            await self._bot_task
        except asyncio.CancelledError:
            pass
        self._logger.manager().info("Бот успешно остановлен")
