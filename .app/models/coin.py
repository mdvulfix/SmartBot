# === file: coin.py ===


"""Представление торгового инструмента (монеты)"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Coin:
    """Криптовалюта с методами для работы на бирже OKX"""
    symbol: str  # Базовый символ (BTC, ETH и т.д.)

    @property
    def symbol_id(self) -> str:
        """Форматированный ID для запросов к API OKX"""
        return f"{self.symbol}-USDT-SWAP" if self.symbol != "USDT" else "USDT"

    def __str__(self) -> str:
        return self.symbol
