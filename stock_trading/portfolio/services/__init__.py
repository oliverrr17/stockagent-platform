from dataclasses import dataclass
from decimal import Decimal


from dataclasses import dataclass


@dataclass
class HKStockStats:
    stock_code: str
    stock_name: str
    weighted_avg_cost: Decimal
    quantity: int
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl: Decimal
    daily_pnl: Decimal
