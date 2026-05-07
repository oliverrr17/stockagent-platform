import type {
  NewsCategory,
  NewsItem,
  NotificationChannel,
  NotificationStatus,
  PositionOrigin,
  PositionStatus,
  TradeIntentSnapshot,
  TradeDirection,
  TradeMarket,
} from "../types";

type Meta = {
  label: string;
  color?: string;
};

const MARKET_META: Record<TradeMarket, Meta> = {
  A_STOCK: { label: "A股", color: "geekblue" },
  HK_STOCK: { label: "港股", color: "gold" },
};

const DIRECTION_META: Record<TradeDirection, Meta> = {
  BUY: { label: "买入", color: "green" },
  SELL: { label: "卖出", color: "volcano" },
};

const POSITION_STATUS_META: Record<PositionStatus, Meta> = {
  ACTIVE: { label: "持有中", color: "green" },
  CLEARED: { label: "已清仓", color: "default" },
};

const POSITION_ORIGIN_META: Record<PositionOrigin, Meta> = {
  MANUAL: { label: "手动初始化", color: "processing" },
  SYNCED: { label: "自动同步", color: "default" },
};

const NEWS_CATEGORY_META: Record<NewsCategory, Meta> = {
  ANNOUNCEMENT: { label: "公告", color: "blue" },
  SENTIMENT: { label: "舆情", color: "gold" },
  RESEARCH: { label: "研报", color: "purple" },
  INDUSTRY: { label: "行业", color: "cyan" },
};

const PRIORITY_META: Record<NewsItem["priority_level"], Meta> = {
  P1: { label: "即时", color: "red" },
  P2: { label: "摘要", color: "orange" },
  P3: { label: "仅入库", color: "default" },
};

const SOURCE_LABELS: Record<string, string> = {
  THS: "同花顺",
  HSBC_EMAIL: "汇丰邮件",
  MANUAL: "手动录入",
  EASTMONEY: "东方财富",
  SINA_FINANCE: "新浪财经",
  AASTOCKS: "AASTOCKS",
};

const NOTIFICATION_STATUS_META: Record<NotificationStatus, Meta> = {
  SUCCESS: { label: "成功", color: "green" },
  FAILED: { label: "失败", color: "red" },
  PENDING: { label: "待发送", color: "orange" },
};

const NOTIFICATION_CHANNEL_META: Record<NotificationChannel, Meta> = {
  EMAIL: { label: "邮件", color: "geekblue" },
  WECHAT: { label: "微信", color: "green" },
  TELEGRAM: { label: "Telegram", color: "blue" },
};

const INTENT_TAG_LABELS: Record<string, string> = {
  breakout: "突破",
  trend_follow: "趋势跟随",
  pullback: "回踩",
  rebound: "反弹",
  low_absorption: "低吸",
  stop_loss_exit: "止损离场",
  profit_take: "止盈兑现",
  reduce_position: "减仓",
  market_strong: "市场偏强",
  market_neutral: "市场中性",
  market_weak: "市场偏弱",
  sector_hot: "行业偏热",
  sector_neutral: "行业中性",
  sector_cold: "行业偏冷",
  rotation_trade: "轮动交易",
  leader: "龙头",
  follower: "跟风",
  quality_compounder: "高质量公司",
  event_driven: "事件驱动",
  sentiment_driven: "情绪驱动",
  cyclical: "周期属性",
  disciplined: "执行纪律好",
  calm: "情绪稳定",
  hesitant: "执行犹豫",
  fomo: "FOMO",
  fear_of_drawdown: "怕回撤",
  revenge_trade: "报复交易",
  chasing: "追高",
  early_profit_taking: "过早兑现",
};

export const TRADE_INTENT_OPTIONS = {
  setup_tags: ["breakout", "trend_follow", "pullback", "rebound", "low_absorption", "stop_loss_exit", "profit_take", "reduce_position"],
  market_context_tags: ["market_strong", "market_neutral", "market_weak", "sector_hot", "sector_neutral", "sector_cold", "rotation_trade"],
  security_quality_tags: ["leader", "follower", "quality_compounder", "event_driven", "sentiment_driven", "cyclical"],
  execution_emotion_tags: ["disciplined", "calm", "hesitant", "fomo", "fear_of_drawdown", "revenge_trade", "chasing", "early_profit_taking"],
} as const;

export function marketMeta(value: TradeMarket): Meta {
  return MARKET_META[value];
}

export function directionMeta(value: TradeDirection): Meta {
  return DIRECTION_META[value];
}

export function positionStatusMeta(value: PositionStatus): Meta {
  return POSITION_STATUS_META[value];
}

export function positionOriginMeta(value: PositionOrigin): Meta {
  return POSITION_ORIGIN_META[value];
}

export function newsCategoryMeta(value: NewsCategory): Meta {
  return NEWS_CATEGORY_META[value];
}

export function priorityMeta(value: NewsItem["priority_level"]): Meta {
  return PRIORITY_META[value];
}

export function pushedMeta(pushed: boolean): Meta {
  return pushed ? { label: "已推送", color: "green" } : { label: "未推送", color: "default" };
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

export function notificationStatusMeta(value: NotificationStatus): Meta {
  return NOTIFICATION_STATUS_META[value];
}

export function notificationChannelMeta(value: NotificationChannel): Meta {
  return NOTIFICATION_CHANNEL_META[value];
}

export function formatShortDateTime(value: string | number): string {
  const date = new Date(typeof value === "number" ? value : value);
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateTime(value: string | number): string {
  const date = new Date(typeof value === "number" ? value : value);
  return date.toLocaleString("zh-CN");
}

export function tradeIntentTagLabel(value: string): string {
  return INTENT_TAG_LABELS[value] ?? value;
}

export function normalizeTradeIntentSnapshot(snapshot: TradeIntentSnapshot | null | undefined | Record<string, unknown>): TradeIntentSnapshot | null {
  if (!snapshot || typeof snapshot !== "object") {
    return null;
  }

  const readArray = (value: unknown): string[] => (Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []);
  const readString = (value: unknown): string => (typeof value === "string" ? value : "");

  return {
    setup_tags: readArray((snapshot as Record<string, unknown>).setup_tags),
    market_context_tags: readArray((snapshot as Record<string, unknown>).market_context_tags),
    security_quality_tags: readArray((snapshot as Record<string, unknown>).security_quality_tags),
    execution_emotion_tags: readArray((snapshot as Record<string, unknown>).execution_emotion_tags),
    overall_notes: readString((snapshot as Record<string, unknown>).overall_notes),
    planned_holding_period: readString((snapshot as Record<string, unknown>).planned_holding_period),
    planned_stop_loss_type: readString((snapshot as Record<string, unknown>).planned_stop_loss_type),
    planned_stop_loss_value:
      typeof (snapshot as Record<string, unknown>).planned_stop_loss_value === "string"
        ? ((snapshot as Record<string, unknown>).planned_stop_loss_value as string)
        : null,
    planned_take_profit_type: readString((snapshot as Record<string, unknown>).planned_take_profit_type),
    planned_take_profit_value:
      typeof (snapshot as Record<string, unknown>).planned_take_profit_value === "string"
        ? ((snapshot as Record<string, unknown>).planned_take_profit_value as string)
        : null,
  };
}

export function summarizeIntentTags(snapshot: TradeIntentSnapshot | null | undefined): string[] {
  const normalized = normalizeTradeIntentSnapshot(snapshot);
  if (!normalized) {
    return [];
  }
  return [
    ...normalized.setup_tags,
    ...normalized.market_context_tags,
    ...normalized.security_quality_tags,
    ...normalized.execution_emotion_tags,
  ].map(tradeIntentTagLabel);
}
