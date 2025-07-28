# === file: coin.py ===
from dataclasses import dataclass

@dataclass
class Coin:
    base: str
    quote: str = "USDT"

    @property
    def instrument_id(self) -> str:
        return f"{self.base.upper()}-{self.quote.upper()}"
