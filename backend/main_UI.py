# === file: main.py ===

import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from decimal import Decimal
import logging
import threading
import queue
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

# Определяем, с какими монетами работаем
COINS = {
    "BTC": Coin("BTC", instrument_type="SWAP"),
    "ETH": Coin("ETH", instrument_type="SWAP"),
    "SOL": Coin("SOL", instrument_type="SWAP"),
    "XRP": Coin("XRP", instrument_type="SWAP")
}

class ExchangeGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OKX Exchange Controller")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Создаем экземпляр биржи
        symbols = [coin.instrument_id for coin in COINS.values()]
        self.exchange = OkxExchange(symbols)
        
        # Очередь для сообщений из асинхронного потока
        self.message_queue = queue.Queue()
        
        # Создаем интерфейс
        self.create_widgets()
        
        # Запускаем поток для обработки асинхронных операций
        self.running = True
        self.async_thread = threading.Thread(target=self.async_worker, daemon=True)
        self.async_thread.start()
        
        # Запускаем проверку очереди сообщений
        self.check_queue()
        
        # Обновляем статус
        self.update_status()

    def create_widgets(self):
        # Создаем вкладки
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Вкладка управления
        control_frame = ttk.Frame(self.notebook)
        self.notebook.add(control_frame, text="Control")
        
        # Панель управления
        control_panel = ttk.LabelFrame(control_frame, text="Exchange Control")
        control_panel.pack(fill="x", padx=10, pady=10)
        
        self.start_button = ttk.Button(
            control_panel, 
            text="Start Exchange", 
            command=self.start_exchange,
            width=15
        )
        self.start_button.pack(side="left", padx=5, pady=5)
        
        self.stop_button = ttk.Button(
            control_panel, 
            text="Stop Exchange", 
            command=self.stop_exchange,
            state="disabled",
            width=15
        )
        self.stop_button.pack(side="left", padx=5, pady=5)
        
        self.status_label = ttk.Label(
            control_panel, 
            text="Status: DISCONNECTED",
            font=("Arial", 10, "bold")
        )
        self.status_label.pack(side="right", padx=10, pady=5)
        
        # Панель баланса
        balance_frame = ttk.LabelFrame(control_frame, text="Balance")
        balance_frame.pack(fill="x", padx=10, pady=5)
        
        self.balance_label = ttk.Label(
            balance_frame, 
            text="USDT: 0.00",
            font=("Arial", 10)
        )
        self.balance_label.pack(padx=10, pady=5)
        
        # Панель ордеров
        order_frame = ttk.LabelFrame(control_frame, text="Quick Order")
        order_frame.pack(fill="x", padx=10, pady=5)
        
        # Выбор монеты
        ttk.Label(order_frame, text="Coin:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.coin_var = tk.StringVar(value="BTC")
        coin_combo = ttk.Combobox(order_frame, textvariable=self.coin_var, width=10)
        coin_combo['values'] = list(COINS.keys())
        coin_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # Выбор направления
        ttk.Label(order_frame, text="Side:").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.side_var = tk.StringVar(value="buy")
        side_combo = ttk.Combobox(order_frame, textvariable=self.side_var, width=8)
        side_combo['values'] = ["buy", "sell"]
        side_combo.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        # Цена
        ttk.Label(order_frame, text="Price:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.price_entry = ttk.Entry(order_frame, width=15)
        self.price_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        # Размер
        ttk.Label(order_frame, text="Size:").grid(row=1, column=2, padx=5, pady=5, sticky="e")
        self.size_entry = ttk.Entry(order_frame, width=15)
        self.size_entry.grid(row=1, column=3, padx=5, pady=5, sticky="w")
        
        # Кнопка размещения ордера
        self.place_order_button = ttk.Button(
            order_frame, 
            text="Place Order", 
            command=self.place_order,
            width=15
        )
        self.place_order_button.grid(row=1, column=4, padx=10, pady=5)
        
        # Вкладка логов
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="Logs")
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame, 
            wrap=tk.WORD, 
            state="disabled"
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Настраиваем логгер для вывода в текстовое поле
        self.setup_logger()
    
    def setup_logger(self):
        # Создаем обработчик для вывода в текстовое поле
        class TextHandler(logging.Handler):
            def __init__(self, text_widget):
                super().__init__()
                self.text_widget = text_widget
            
            def emit(self, record):
                msg = self.format(record)
                self.text_widget.configure(state="normal")
                self.text_widget.insert(tk.END, msg + "\n")
                self.text_widget.configure(state="disabled")
                self.text_widget.see(tk.END)
        
        # Настраиваем корневой логгер
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Удаляем существующие обработчики
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Добавляем обработчик для текстового поля
        text_handler = TextHandler(self.log_text)
        text_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(text_handler)
        
        # Добавляем обработчик для консоли
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(console_handler)

    def async_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.running:
            try:
                # Обрабатываем сообщения из очереди
                if not self.message_queue.empty():
                    task, *args = self.message_queue.get_nowait()
                    if task == "start":
                        loop.run_until_complete(self.exchange.run())
                    elif task == "stop":
                        loop.run_until_complete(self.exchange.stop())
                    elif task == "place_order":
                        loop.run_until_complete(self.async_place_order(*args))
                    elif task == "update_status":
                        loop.run_until_complete(self.async_update_status())
                
                # Запускаем цикл обработки событий
                loop.run_until_complete(asyncio.sleep(0.1))
            except Exception as e:
                logging.error(f"Async worker error: {e}")
        
        # Завершаем работу
        loop.run_until_complete(self.exchange.close())
        loop.close()

    def check_queue(self):
        try:
            # Обрабатываем все сообщения в очереди
            while not self.message_queue.empty():
                task, *args = self.message_queue.get_nowait()
                if task == "update_ui":
                    self.update_ui(*args)
        except Exception as e:
            logging.error(f"Queue error: {e}")
        
        # Планируем следующую проверку
        self.root.after(500, self.check_queue)

    def start_exchange(self):
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.message_queue.put(("start",))
        logging.info("Starting exchange...")

    def stop_exchange(self):
        self.stop_button.config(state="disabled")
        self.start_button.config(state="normal")
        self.message_queue.put(("stop",))
        logging.info("Stopping exchange...")

    def place_order(self):
        coin = self.coin_var.get()
        side = self.side_var.get()
        price_str = self.price_entry.get()
        size_str = self.size_entry.get()
        
        if not price_str or not size_str:
            messagebox.showerror("Error", "Please enter both price and size")
            return
        
        try:
            price = Decimal(price_str)
            size = Decimal(size_str)
        except:
            messagebox.showerror("Error", "Invalid price or size format")
            return
        
        coin_obj = COINS.get(coin)
        if not coin_obj:
            messagebox.showerror("Error", f"Coin {coin} not supported")
            return
        
        self.message_queue.put(("place_order", coin_obj.instrument_id, side, price, size))
        logging.info(f"Placing order: {coin} {side} {price} {size}")

    async def async_place_order(self, symbol, side, price, size):
        order_id = await self.exchange.place_order(symbol, side, price, size)
        if order_id:
            self.message_queue.put(("update_ui", "info", f"Order placed: ID={order_id}"))
        else:
            self.message_queue.put(("update_ui", "error", "Failed to place order"))

    async def async_update_status(self):
        report = await self.exchange.get_status_report()
        self.message_queue.put(("update_ui", "status", report))

    def update_status(self):
        self.message_queue.put(("update_status",))
        self.root.after(5000, self.update_status)  # Обновлять каждые 5 секунд

    def update_ui(self, update_type, *args):
        if update_type == "status":
            report = args[0]
            status_text = f"Status: {report['state']}"
            self.status_label.config(text=status_text)
            
            # Обновляем цвет в зависимости от состояния
            if report['needs_attention']:
                self.status_label.config(foreground="red")
            elif report['is_operational']:
                self.status_label.config(foreground="green")
            else:
                self.status_label.config(foreground="orange")
            
            # Обновляем баланс
            balance_text = f"USDT: {report['balance']}"
            self.balance_label.config(text=balance_text)
        
        elif update_type == "info":
            messagebox.showinfo("Information", args[0])
        
        elif update_type == "error":
            messagebox.showerror("Error", args[0])

    def on_close(self):
        self.running = False
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ExchangeGUI(root)
    app.update_status()  # Запускаем периодическое обновление статуса
    root.mainloop()