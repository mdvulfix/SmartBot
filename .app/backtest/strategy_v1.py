class SimpleStrategy:
    """
    Простейшая стратегия для примера:
    - Покупает, если цена закрытия > предыдущей
    - Продает, если цена закрытия < предыдущей
    """

    def __init__(self):
        self.positions = []
        self.trades = []

    def on_data(self, row):
        if not self.positions:
            self.positions.append(("BUY", row["close"], row["timestamp"]))
            self.trades.append({"action": "BUY", "price": row["close"], "time": row["timestamp"]})
        else:
            last_action = self.positions[-1][0]
            if last_action == "BUY" and row["close"] < self.positions[-1][1]:
                self.positions.append(("SELL", row["close"], row["timestamp"]))
                self.trades.append({"action": "SELL", "price": row["close"], "time": row["timestamp"]})
            elif last_action == "SELL" and row["close"] > self.positions[-1][1]:
                self.positions.append(("BUY", row["close"], row["timestamp"]))
                self.trades.append({"action": "BUY", "price": row["close"], "time": row["timestamp"]})

    def get_results(self):
        return self.trades
    

    
