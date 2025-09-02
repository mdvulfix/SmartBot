import pandas as pd

class BacktestRunner:
    def __init__(self, strategy, data: pd.DataFrame):
        self.strategy = strategy
        self.data = data

    def run(self):
        for _, row in self.data.iterrows():
            self.strategy.on_data(row)
        return self.strategy.get_results()