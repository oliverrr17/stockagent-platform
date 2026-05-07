SETUP_TAGS = (
    "breakout",
    "trend_follow",
    "pullback",
    "rebound",
    "low_absorption",
    "stop_loss_exit",
    "profit_take",
    "reduce_position",
)

MARKET_CONTEXT_TAGS = (
    "market_strong",
    "market_neutral",
    "market_weak",
    "sector_hot",
    "sector_neutral",
    "sector_cold",
    "rotation_trade",
)

SECURITY_QUALITY_TAGS = (
    "leader",
    "follower",
    "quality_compounder",
    "event_driven",
    "sentiment_driven",
    "cyclical",
)

EXECUTION_EMOTION_TAGS = (
    "disciplined",
    "calm",
    "hesitant",
    "fomo",
    "fear_of_drawdown",
    "revenge_trade",
    "chasing",
    "early_profit_taking",
)

PLANNED_HOLDING_PERIODS = (
    "intraday",
    "swing",
    "position",
)

PLANNED_STOP_LOSS_TYPES = (
    "fixed_price",
    "structure_low",
    "moving_average",
    "trailing_stop",
)

PLANNED_TAKE_PROFIT_TYPES = (
    "fixed_price",
    "prior_high",
    "rr_multiple",
    "trailing_exit",
)

INTENT_TAG_CHOICES = {
    "setup_tags": set(SETUP_TAGS),
    "market_context_tags": set(MARKET_CONTEXT_TAGS),
    "security_quality_tags": set(SECURITY_QUALITY_TAGS),
    "execution_emotion_tags": set(EXECUTION_EMOTION_TAGS),
}
