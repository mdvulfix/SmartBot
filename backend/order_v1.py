from utils import Utils
from coin import Coin
from enum import Enum

class TradeMode(Enum):
    NONE = ''
    ISOLATED = 'isolated'
    CROSS = 'cross'

class TradeSide(Enum):
    NONE = ''
    BUY = 'buy'
    SELL = 'sell'

class OrderType(Enum):
    NONE = ''
    LIMIT = 'limit'
    MARKET = 'market'  

class Order:
    def __init__(self, ordType: OrderType, tdMode: TradeMode, side: TradeSide, coin: Coin, price: str, size: str):
        self._logger = Utils.get_logger("trade_strategy")
        
        self._ordType = ordType
        self._tdMode = tdMode
        self._side = side
        self._coin = coin
        self._price = price
        self._size = size
        
