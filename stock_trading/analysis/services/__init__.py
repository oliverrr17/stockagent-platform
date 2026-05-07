from dataclasses import dataclass


@dataclass
class VolumeRatios:
    vol_to_ma5: float
    vol_to_ma10: float
    vol_to_ma20: float
    is_high_volume: bool
    is_low_volume: bool


class VolumePattern:
    VOL_UP_PRICE_UP = "量增价涨"
    VOL_UP_PRICE_DOWN = "量增价跌"
    VOL_DOWN_PRICE_UP = "缩量上涨"
    VOL_DOWN_PRICE_DOWN = "缩量下跌"


class TrendPhase:
    UPTREND = "上升趋势"
    DOWNTREND = "下降趋势"
    SIDEWAYS = "横盘整理"


class PricePosition:
    TRAPPED = "套牢区"
    PROFIT = "获利区"
    DENSE = "密集成交区"

