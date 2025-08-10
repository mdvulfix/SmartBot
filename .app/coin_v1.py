# === file: coin.py ===

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
