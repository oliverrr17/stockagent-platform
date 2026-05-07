export type TradeMarket = "A_STOCK" | "HK_STOCK";
export type TradeDirection = "BUY" | "SELL";
export type TradeSource = "THS" | "HSBC_EMAIL" | "MANUAL";
export type PositionStatus = "ACTIVE" | "CLEARED";
export type PositionOrigin = "MANUAL" | "SYNCED";
export type NotificationStatus = "SUCCESS" | "FAILED" | "PENDING";
export type NotificationChannel = "EMAIL" | "WECHAT" | "TELEGRAM";

export interface TradeIntentSnapshot {
  setup_tags: string[];
  market_context_tags: string[];
  security_quality_tags: string[];
  execution_emotion_tags: string[];
  overall_notes: string;
  planned_holding_period: string;
  planned_stop_loss_type: string;
  planned_stop_loss_value: string | null;
  planned_take_profit_type: string;
  planned_take_profit_value: string | null;
}

export interface TradeRecord {
  id: number;
  stock_code: string;
  stock_name: string;
  market: TradeMarket;
  direction: TradeDirection;
  price: string;
  quantity: number;
  commission: string;
  stamp_duty: string;
  other_fees: string;
  trade_time: string;
  source: TradeSource | string;
  created_at: string;
  intent_snapshot?: TradeIntentSnapshot | null;
}

export interface TradeCreatePayload {
  stock_code: string;
  stock_name: string;
  market: TradeMarket;
  direction: TradeDirection;
  price: string;
  quantity: number;
  trade_time: string;
  source: TradeSource;
  commission?: string;
  stamp_duty?: string;
  other_fees?: string;
  intent_snapshot?: TradeIntentSnapshot | null;
}

export interface Position {
  id: number;
  stock_code: string;
  stock_name: string;
  market: TradeMarket;
  quantity: number;
  cost_price: string;
  weighted_avg_cost: string;
  total_invested: string;
  realized_pnl: string;
  status: PositionStatus;
  origin: PositionOrigin;
  manual_entry_count: number;
  created_at: string;
  updated_at: string;
}

export interface HKStockStats {
  stock_code: string;
  stock_name: string;
  weighted_avg_cost: string;
  quantity: number;
  market_value: string;
  unrealized_pnl: string;
  unrealized_pnl_pct: string;
  realized_pnl: string;
  daily_pnl: string;
}

export interface PositionEntryPayload {
  stock_code: string;
  stock_name: string;
  market: TradeMarket;
  quantity: number;
  cost_price: string;
  entry_time: string;
}

export type CashCurrency = "CNY" | "HKD";
export type CashFlowDirection = "DEPOSIT" | "WITHDRAWAL";

export interface CashAccount {
  id: number;
  currency: CashCurrency;
  label: string;
  balance: number;
  created_at: string;
  updated_at: string;
}

export interface CashFlow {
  id: number;
  cash_account: number;
  currency: CashCurrency;
  direction: CashFlowDirection;
  amount: string;
  occurred_at: string;
  note: string;
  created_at: string;
}

export interface CashFlowPayload {
  currency: CashCurrency;
  direction: CashFlowDirection;
  amount: string;
  occurred_at: string;
  note?: string;
}

export interface PortfolioPositionAnalytics {
  stock_code: string;
  stock_name: string;
  market: TradeMarket;
  quantity: number;
  latest_price: number;
  previous_close: number;
  cost_basis_native: number;
  market_value_native: number;
  market_value_cny: number;
  unrealized_pnl_native: number;
  unrealized_pnl_cny: number;
  daily_pnl_native: number;
  daily_pnl_cny: number;
  return_pct: number;
  currency: CashCurrency;
  fx_rate: number;
  data_source: string;
  degraded: boolean;
  degraded_reason: string;
}

export interface PortfolioClearedPosition {
  stock_code: string;
  stock_name: string;
  market: TradeMarket;
  quantity: number;
  status: PositionStatus;
  realized_pnl_native: number;
  realized_pnl_cny: number;
  updated_at: string;
}

export interface PortfolioOverview {
  base_currency: "CNY";
  start_date: string;
  valuation_date?: string;
  audit_status?: "FINAL" | "PROVISIONAL";
  cash_balances: {
    CNY: { balance: number; balance_cny: number };
    HKD: { balance: number; balance_cny: number; fx_rate: number };
  };
  positions_market_value_cny: number;
  total_assets_cny: number;
  realized_pnl_cny: number;
  unrealized_pnl_cny: number;
  total_return_cny: number;
  returns: {
    daily: number;
    monthly: number;
    yearly: number;
  };
  curves: {
    daily: Array<{
      date: string;
      total_assets_cny: number;
      total_return_cny: number;
      daily_return_pct: number;
      cumulative_return_pct: number;
    }>;
    monthly: Array<{
      date: string;
      total_assets_cny: number;
      total_return_cny: number;
      daily_return_pct: number;
      cumulative_return_pct: number;
    }>;
    yearly: Array<{
      date: string;
      total_assets_cny: number;
      total_return_cny: number;
      daily_return_pct: number;
      cumulative_return_pct: number;
    }>;
  };
}

export interface PortfolioDailyContribution {
  stock_code: string;
  stock_name: string;
  market: TradeMarket;
  start_quantity: number;
  end_quantity: number;
  previous_close: number;
  latest_price: number;
  trade_cash_delta: number;
  daily_pnl_native: number;
  daily_pnl_cny: number;
  fx_rate: number;
  price_source: string;
  source_trade_date: string | null;
  degraded: boolean;
  degraded_reason: string;
  audit_status: "FINAL" | "PROVISIONAL";
}

export interface PortfolioDailyContributionResponse {
  snapshot_date: string;
  audit_status: "FINAL" | "PROVISIONAL";
  external_flow_cny: number;
  computed_daily_pnl_cny: number;
  contributions: PortfolioDailyContribution[];
}

export type NewsCategory = "ANNOUNCEMENT" | "SENTIMENT" | "RESEARCH" | "INDUSTRY";

export interface NewsItem {
  id: number;
  stock_code: string;
  title: string;
  source: string;
  category: NewsCategory;
  summary: string;
  url: string;
  pushed: boolean;
  published_at: string;
  created_at: string;
  priority_score: number;
  priority_level: "P1" | "P2" | "P3";
  matched_rules: string[];
  latest_notification_status: NotificationStatus | "";
  latest_notification_channel: NotificationChannel | "";
  notification_count: number;
}

export interface OperationsStatus {
  counts: {
    active_positions: number;
    trades_total: number;
    news_total: number;
    news_pending: number;
    news_pushed: number;
    notification_logs: number;
  };
  scheduler: {
    ths: string;
    hsbc: string;
    news_fetch: string;
    news_digest: string;
  };
  alerts: Array<{
    severity: "warning" | "error" | "info";
    title: string;
    message: string;
  }>;
  recent_logs: Array<{
    name: string;
    updated_at: number;
    last_line: string;
    preview: string[];
  }>;
}

export interface ReviewReport {
  id: number;
  trade_record: number;
  report_kind: string;
  engine_version: string;
  version: number;
  is_latest: boolean;
  volume_analysis: Record<string, unknown>;
  chip_analysis: Record<string, unknown>;
  trend_analysis: Record<string, unknown>;
  intent_snapshot: TradeIntentSnapshot | null;
  objective_summary: {
    market_heat: string;
    industry_heat: string;
    company_quality: string;
  };
  intent_gap_diagnosis: {
    gap_level: string;
    gap_items: string[];
  };
  subscores: {
    decision_quality: number;
    context_alignment: number;
    execution_quality: number;
    risk_discipline: number;
    emotion_discipline: number;
  };
  coach_report_payload: {
    user_intent_summary: string;
    objective_context_summary: string;
    overall_verdict: string;
    setup_review: string;
    execution_review: string;
    risk_plan_review: string;
    exit_review: string;
    pnl_attribution: string;
    pattern_tag: string;
    follow_up_advice: string;
    next_time_rules: string[];
    missing_data_notes: string[];
  };
  evidence_payload: Record<string, unknown>;
  overall_score: number;
  created_at: string;
  trade_summary: {
    id: number;
    stock_code: string;
    stock_name: string;
    market: TradeMarket;
    direction: TradeDirection;
    price: string;
    quantity: number;
    trade_time: string;
    source: string;
  };
  trade_intent_snapshot?: TradeIntentSnapshot | null;
}

export interface NotificationLog {
  id: number;
  news_item: number;
  stock_code: string;
  news_title: string;
  news_source: string;
  news_category: NewsCategory;
  news_published_at: string;
  channel: NotificationChannel;
  status: NotificationStatus;
  retry_count: number;
  sent_at: string | null;
  priority_score: number;
  priority_level: "P1" | "P2" | "P3";
  matched_rules: string[];
}

export interface OperationsActionResult {
  action: string;
  [key: string]: unknown;
}
