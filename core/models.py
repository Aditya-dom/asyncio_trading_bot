from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"

class OrderStatus(Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    PENDING_CANCEL = "PENDING_CANCEL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

@dataclass
class Ticker:
    symbol: str
    price: float
    change_percent: float
    volume: float
    timestamp: datetime

@dataclass
class Balance:
    asset: str
    free: float
    locked: float
    
    @property
    def total(self) -> float:
        return self.free + self.locked

@dataclass
class Order:
    symbol: str
    order_id: int
    client_order_id: str
    side: OrderSide
    type: OrderType
    status: OrderStatus
    quantity: float
    price: Optional[float]
    executed_quantity: float
    quote_quantity: float
    timestamp: datetime
    raw_data: Dict[str, Any]

@dataclass
class Trade:
    symbol: str
    trade_id: int
    order_id: int
    price: float
    quantity: float
    commission: float
    commission_asset: str
    timestamp: datetime
    is_buyer: bool

@dataclass
class Kline:
    symbol: str
    open_time: datetime
    close_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    number_of_trades: int

@dataclass
class OrderBook:
    symbol: str
    bids: list
    asks: list
    last_update_id: int
    timestamp: datetime
