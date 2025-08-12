# === file: position.py ===

from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Any, List, Dict, Optional
from collections import defaultdict

class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    HEDGED = "hedged"

class Position:
    def __init__(
        self,
        position_id: str,
        coin: str,
        strategy: str,
        initial_size: Decimal,
        entry_price: Decimal
    ):
        self.id = position_id
        self.coin = coin
        self.strategy = strategy
        self.created_at = datetime.utcnow()
        self.updated_at = self.created_at
        self.status = PositionStatus.OPEN
        
        # Основные метрики
        self.current_size = initial_size
        self.entry_price = entry_price
        self.current_price = entry_price
        self.realized_pnl = Decimal('0')
        self.unrealized_pnl = Decimal('0')
        self.total_fees = Decimal('0')
        
        # Детализация сделок
        self.buys: List[Dict] = []
        self.sells: List[Dict] = []
        self.orders: List[str] = []  # IDs связанных ордеров
        
        # Аналитические данные
        self.max_profit = Decimal('0')
        self.max_drawdown = Decimal('0')
        self.duration = 0  # в секундах
        
        # Рассчитываем начальные значения
        self._update_pnl()

    def add_order(self, order_id: str, side: str, size: Decimal, price: Decimal, fee: Decimal):
        """Добавляет ордер к позиции и обновляет метрики"""
        self.orders.append(order_id)
        self.updated_at = datetime.utcnow()
        
        if side == 'buy':
            # Обновляем среднюю цену входа
            total_cost = (self.current_size * self.entry_price) + (size * price)
            self.current_size += size
            self.entry_price = total_cost / self.current_size
            
            self.buys.append({
                'order_id': order_id,
                'size': size,
                'price': price,
                'timestamp': self.updated_at
            })
        else:  # sell
            # Реализуем часть позиции
            realized_size = min(size, self.current_size)
            realized_pnl = realized_size * (price - self.entry_price)
            self.realized_pnl += realized_pnl
            self.current_size -= realized_size
            
            self.sells.append({
                'order_id': order_id,
                'size': size,
                'price': price,
                'timestamp': self.updated_at,
                'realized_pnl': realized_pnl
            })
            
            # Если позиция закрыта
            if self.current_size <= Decimal('0.00000001'):  # учет ошибок округления
                self.close()
        
        self.total_fees += fee
        self._update_pnl()

    def update_price(self, new_price: Decimal):
        """Обновляет текущую рыночную цену и пересчитывает PnL"""
        self.current_price = new_price
        self._update_pnl()
        self.updated_at = datetime.utcnow()

    def _update_pnl(self):
        """Пересчитывает реализованный и нереализованный PnL"""
        # Нереализованный PnL
        if self.current_size > 0:
            self.unrealized_pnl = self.current_size * (self.current_price - self.entry_price)
        else:
            self.unrealized_pnl = Decimal('0')
        
        # Обновляем максимальную прибыль и просадку
        total_pnl = self.realized_pnl + self.unrealized_pnl
        if total_pnl > self.max_profit:
            self.max_profit = total_pnl
        
        current_drawdown = self.max_profit - total_pnl
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown

    def close(self):
        """Закрывает позицию"""
        if self.status == PositionStatus.OPEN:
            self.status = PositionStatus.CLOSED
            self.updated_at = datetime.utcnow()
            self.duration = (self.updated_at - self.created_at).total_seconds()
            
            # Финализируем PnL
            self._update_pnl()
            self.realized_pnl += self.unrealized_pnl
            self.unrealized_pnl = Decimal('0')

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "coin": self.coin,
            "strategy": self.strategy,
            "status": self.status.value,
            "size": str(self.current_size),
            "entry_price": str(self.entry_price),
            "current_price": str(self.current_price),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "total_pnl": str(self.realized_pnl + self.unrealized_pnl),
            "total_fees": str(self.total_fees),
            "max_profit": str(self.max_profit),
            "max_drawdown": str(self.max_drawdown),
            "duration": self.duration,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "num_buys": len(self.buys),
            "num_sells": len(self.sells)
        }
    
class PositionManager:
    def __init__(self):
        self.active_positions: Dict[str, Position] = {}
        self.closed_positions: Dict[str, Position] = {}
        self.positions_by_coin = defaultdict(list)
        self.positions_by_strategy = defaultdict(list)
        self.position_counter = 0

    def open_position(
        self,
        coin: str,
        strategy: str,
        size: Decimal,
        price: Decimal
    ) -> Position:
        """Открывает новую позицию"""
        position_id = f"pos-{self.position_counter}-{datetime.utcnow().strftime('%Y%m%d')}"
        self.position_counter += 1
        
        position = Position(
            position_id=position_id,
            coin=coin,
            strategy=strategy,
            initial_size=size,
            entry_price=price
        )
        
        self.active_positions[position_id] = position
        self.positions_by_coin[coin].append(position_id)
        self.positions_by_strategy[strategy].append(position_id)
        
        return position

    def add_order_to_position(
        self,
        position_id: str,
        order_id: str,
        side: str,
        size: Decimal,
        price: Decimal,
        fee: Decimal
    ):
        """Добавляет ордер к существующей позиции"""
        if position_id in self.active_positions:
            position = self.active_positions[position_id]
            position.add_order(order_id, side, size, price, fee)
            
            # Если позиция закрыта, перемещаем в архив
            if position.status == PositionStatus.CLOSED:
                self._close_position(position_id)

    def update_position_price(self, position_id: str, price: Decimal):
        """Обновляет цену для позиции"""
        if position_id in self.active_positions:
            self.active_positions[position_id].update_price(price)

    def close_position(self, position_id: str):
        """Принудительно закрывает позицию"""
        if position_id in self.active_positions:
            position = self.active_positions[position_id]
            position.close()
            self._close_position(position_id)

    def _close_position(self, position_id: str):
        """Перемещает позицию в закрытые"""
        position = self.active_positions.pop(position_id)
        self.closed_positions[position_id] = position

    def get_position(self, position_id: str) -> Optional[Position]:
        """Возвращает позицию по ID"""
        if position_id in self.active_positions:
            return self.active_positions[position_id]
        return self.closed_positions.get(position_id)

    def get_position_for_order(self, order_id: str) -> Optional[Position]:
        """Находит позицию по ID ордера"""
        for position in self.active_positions.values():
            if order_id in position.orders:
                return position
        for position in self.closed_positions.values():
            if order_id in position.orders:
                return position
        return None

    def get_active_positions(self) -> List[Position]:
        return list(self.active_positions.values())

    def get_closed_positions(self) -> List[Position]:
        return list(self.closed_positions.values())

    def calculate_strategy_performance(self, strategy: str) -> Dict[str, Any]:
        """Анализирует производительность стратегии"""
        active_positions = []
        closed_positions = []
        
        for position_id in self.positions_by_strategy.get(strategy, []):
            position = self.get_position(position_id)
            if position:
                if position.status == PositionStatus.OPEN:
                    active_positions.append(position)
                else:
                    closed_positions.append(position)
        
        return self._analyze_positions(active_positions, closed_positions)

    def _analyze_positions(self, active: List[Position], closed: List[Position]) -> Dict[str, Any]:
        """Анализирует набор позиций"""
        total_realized = Decimal('0')
        total_unrealized = Decimal('0')
        total_fees = Decimal('0')
        winning_positions = 0
        losing_positions = 0
        
        for pos in closed:
            total_realized += pos.realized_pnl
            total_fees += pos.total_fees
            if pos.realized_pnl > 0:
                winning_positions += 1
            else:
                losing_positions += 1
        
        for pos in active:
            total_unrealized += pos.unrealized_pnl
            total_fees += pos.total_fees
        
        total_positions = len(active) + len(closed)
        win_rate = winning_positions / len(closed) if closed else 0
        
        return {
            "total_positions": total_positions,
            "active_positions": len(active),
            "closed_positions": len(closed),
            "win_rate": win_rate,
            "total_realized_pnl": str(total_realized),
            "total_unrealized_pnl": str(total_unrealized),
            "total_fees": str(total_fees),
            "net_profit": str(total_realized + total_unrealized - total_fees),
            "avg_position_duration": self._avg_duration(closed),
            "profit_factor": winning_positions / losing_positions if losing_positions else float('inf')
        }

    def _avg_duration(self, positions: List[Position]) -> float:
        """Средняя продолжительность позиций"""
        if not positions:
            return 0
        total_duration = sum(p.duration for p in positions)
        return total_duration / len(positions)