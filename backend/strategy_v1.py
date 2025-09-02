from utils import Utils

class Strategy:
    def __init__(self):
        self._logger = Utils.get_logger("trade_strategy")

        self._grid = {}

    def create_grid(self):
        self._grid.clear()
        current_price = self.get_current_price()
        step = Decimal(str(self.grid_step_pct)) / Decimal('100')
        for i in range(1, self.grid_num + 1):
            self.grid_levels.append({"price": current_price * (1 - step * i), "side": "buy"})
            self.grid_levels.append({"price": current_price * (1 + step * i), "side": "sell"})
        self._logger.info(f"Created grid with {len(self.grid_levels)} levels.")

    def adjust_grid(self, new_price):
        threshold = self.grid_levels[0]['price'] * Decimal('0.05')
        if abs(new_price - self.reference_price) > threshold:
            self._logger.info("Price moved significantly, adjusting grid")
            old_reference = self.reference_price
            self.create_grid()
            self.reference_price = new_price
            self._logger.info(f"Grid adjusted. Reference price updated from {old_reference} to {new_price}")