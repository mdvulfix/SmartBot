# === file: coin.py ===
from dataclasses import dataclass
from typing import Any, Tuple, Optional, List, Dict
from decimal import Decimal

@dataclass
class Coin:
    
    # Symbol cache for min lot size
    SYMBOL_CACHE: Dict[str, Dict[str, Decimal]] = {}
    # Symbol precision cache
    SYMBOL_PRECISION_CACHE: Dict[str, Tuple[int, int]] = {}

    def __init__(self, symbol: str):
        self._symbol: str = symbol.upper()
    
    @property
    def id(self) -> str:
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

    async def get_symbol_details(self) -> Dict[str, Decimal]:
 
        if self._symbol in SYMBOL_CACHE:
            return SYMBOL_CACHE[self._symbol]

        # Определяем тип инструмента по символу
        inst_type = "SWAP" if "SWAP" in symbol else "SPOT"
        
        data, ok = await self.request(
            "GET", "/api/v5/public/instruments",
            {"instType": inst_type, "instId": symbol}
        )
        
        if not ok or not data or not isinstance(data, list):
            self._logger.error(f"Failed to get instrument details for {symbol}")
            return {
                "minSz": Decimal("0.01"),
                "lotSz": Decimal("0.01"),
                "tickSz": Decimal("0.01"),
                "ctVal": Decimal("1"),
                "ctType": "linear"
            }

        try:
            instrument = data[0]
            details = {
                "minSz": Decimal(instrument.get("minSz", "0.01")),
                "lotSz": Decimal(instrument.get("lotSz", "0.01")),
                "tickSz": Decimal(instrument.get("tickSz", "0.01")),
                "ctVal": Decimal(instrument.get("ctVal", "1")),
                "ctType": instrument.get("ctType", "linear")
            }
            self._instrument_cache[symbol] = details
            return details
        except Exception as e:
            self._logger.error(f"Error parsing instrument details: {e}")
            return {
                "minSz": Decimal("0.01"),
                "lotSz": Decimal("0.01"),
                "tickSz": Decimal("0.01"),
                "ctVal": Decimal("1"),
                "ctType": "linear"
            }
