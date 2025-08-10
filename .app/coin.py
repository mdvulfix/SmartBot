# === file: coin.py ===
from dataclasses import dataclass
from typing import Any, Tuple, Optional, List, Dict
from decimal import Decimal

class Coin:
    
    # Symbol cache for min lot size
    SYMBOL_CACHE: Dict[str, Dict[str, Any]] = {}
    # Symbol precision cache
    SYMBOL_PRECISION_CACHE: Dict[str, Tuple[int, int]] = {}
    
    def __init__(self, symbol: str):
        self._symbol: str = symbol.upper()

    @property
    def symbol_id(self) -> str:
        if self._symbol == "USDT":
            return "USDT"
        else:
            return f"{self._symbol}-USDT-SWAP"
    
    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def symbol_min_lot_size(self) -> Decimal:
        return Decimal("0.00")
    
    @property
    def symbol_precision(self) -> int:
        return 0
