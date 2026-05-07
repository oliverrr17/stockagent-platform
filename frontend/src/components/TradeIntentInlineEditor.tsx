import { Button, Input, Space, Tag } from "antd";
import { useEffect, useMemo, useState } from "react";
import type { TradeIntentSnapshot, TradeRecord } from "../types";
import { TRADE_INTENT_OPTIONS, tradeIntentTagLabel } from "../utils/display";

const EMPTY_INTENT_SNAPSHOT: TradeIntentSnapshot = {
  setup_tags: [],
  market_context_tags: [],
  security_quality_tags: [],
  execution_emotion_tags: [],
  overall_notes: "",
  planned_holding_period: "",
  planned_stop_loss_type: "",
  planned_stop_loss_value: null,
  planned_take_profit_type: "",
  planned_take_profit_value: null,
};

function sanitizeIntentSnapshot(snapshot: TradeIntentSnapshot): TradeIntentSnapshot {
  const normalizeTags = (values: string[]) => Array.from(new Set(values.filter(Boolean)));
  const normalizeDecimal = (value: string | null) => {
    if (value === null || String(value).trim() === "") {
      return null;
    }
    return Number(value).toFixed(4);
  };

  return {
    setup_tags: normalizeTags(snapshot.setup_tags),
    market_context_tags: normalizeTags(snapshot.market_context_tags),
    security_quality_tags: normalizeTags(snapshot.security_quality_tags),
    execution_emotion_tags: normalizeTags(snapshot.execution_emotion_tags),
    overall_notes: snapshot.overall_notes.trim(),
    planned_holding_period: snapshot.planned_holding_period,
    planned_stop_loss_type: snapshot.planned_stop_loss_type,
    planned_stop_loss_value: normalizeDecimal(snapshot.planned_stop_loss_value),
    planned_take_profit_type: snapshot.planned_take_profit_type,
    planned_take_profit_value: normalizeDecimal(snapshot.planned_take_profit_value),
  };
}

type MultiTagField =
  | "setup_tags"
  | "market_context_tags"
  | "security_quality_tags"
  | "execution_emotion_tags";

type TradeIntentInlineEditorProps = {
  trade: TradeRecord;
  saving: boolean;
  onSave: (tradeId: number, snapshot: TradeIntentSnapshot) => Promise<void>;
};

function renderCheckboxGroup(
  tradeId: number,
  title: string,
  field: MultiTagField,
  snapshot: TradeIntentSnapshot,
  toggleTag: (field: MultiTagField, value: string) => void,
  ariaSuffix: string,
) {
  return (
    <fieldset className="intent-fieldset">
      <legend>{title}</legend>
      <div className="intent-checkbox-grid">
        {TRADE_INTENT_OPTIONS[field].map((option) => (
          <label key={`${tradeId}-${field}-${option}`} className="intent-checkbox-item">
            <input
              type="checkbox"
              aria-label={`trade-intent-${tradeId}-${ariaSuffix}-${option}`}
              checked={snapshot[field].includes(option)}
              onChange={() => toggleTag(field, option)}
            />
            <span>{tradeIntentTagLabel(option)}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function TradeIntentInlineEditor({ trade, saving, onSave }: TradeIntentInlineEditorProps) {
  const [draft, setDraft] = useState<TradeIntentSnapshot>(trade.intent_snapshot ?? EMPTY_INTENT_SNAPSHOT);
  const hasAnyValue = useMemo(() => {
    const snapshot = trade.intent_snapshot;
    if (!snapshot) {
      return false;
    }
    return Boolean(
      snapshot.setup_tags.length ||
        snapshot.market_context_tags.length ||
        snapshot.security_quality_tags.length ||
        snapshot.execution_emotion_tags.length ||
        snapshot.overall_notes ||
        snapshot.planned_holding_period ||
        snapshot.planned_stop_loss_type ||
        snapshot.planned_stop_loss_value ||
        snapshot.planned_take_profit_type ||
        snapshot.planned_take_profit_value,
    );
  }, [trade.intent_snapshot]);

  useEffect(() => {
    setDraft(trade.intent_snapshot ?? EMPTY_INTENT_SNAPSHOT);
  }, [trade.id, trade.intent_snapshot]);

  const updateText = (field: keyof TradeIntentSnapshot, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const toggleTag = (field: MultiTagField, value: string) => {
    setDraft((current) => {
      const values = current[field];
      const nextValues = values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
      return { ...current, [field]: nextValues };
    });
  };

  return (
    <details className="row-intent-editor">
      <summary aria-label={`trade-intent-toggle-${trade.id}`} className="row-intent-summary">
        <span>{hasAnyValue ? "编辑标签 / 已填写" : "编辑标签"}</span>
      </summary>
      <div className="row-intent-panel">
        {renderCheckboxGroup(trade.id, "Setup 标签", "setup_tags", draft, toggleTag, "setup")}
        {renderCheckboxGroup(trade.id, "市场环境标签", "market_context_tags", draft, toggleTag, "market")}
        {renderCheckboxGroup(trade.id, "标的质量标签", "security_quality_tags", draft, toggleTag, "quality")}
        {renderCheckboxGroup(trade.id, "执行与情绪标签", "execution_emotion_tags", draft, toggleTag, "emotion")}

        <label>
          整体备注
          <Input.TextArea
            aria-label={`trade-intent-${trade.id}-overall-notes`}
            rows={3}
            value={draft.overall_notes}
            onChange={(event) => updateText("overall_notes", event.target.value)}
          />
        </label>

        <div className="row-intent-plan-grid">
          <label>
            计划持有周期
            <select
              aria-label={`trade-intent-${trade.id}-holding-period`}
              value={draft.planned_holding_period}
              onChange={(event) => updateText("planned_holding_period", event.target.value)}
            >
              <option value="">未填写</option>
              <option value="intraday">日内</option>
              <option value="swing">波段</option>
              <option value="position">持仓</option>
            </select>
          </label>
          <label>
            计划止损类型
            <select
              aria-label={`trade-intent-${trade.id}-stop-loss-type`}
              value={draft.planned_stop_loss_type}
              onChange={(event) => updateText("planned_stop_loss_type", event.target.value)}
            >
              <option value="">未填写</option>
              <option value="fixed_price">固定价</option>
              <option value="structure_low">结构低点</option>
              <option value="moving_average">均线失守</option>
              <option value="trailing_stop">移动止损</option>
            </select>
          </label>
          <label>
            计划止损价
            <Input
              aria-label={`trade-intent-${trade.id}-stop-loss-value`}
              inputMode="decimal"
              value={draft.planned_stop_loss_value ?? ""}
              onChange={(event) => updateText("planned_stop_loss_value", event.target.value)}
            />
          </label>
          <label>
            计划止盈类型
            <select
              aria-label={`trade-intent-${trade.id}-take-profit-type`}
              value={draft.planned_take_profit_type}
              onChange={(event) => updateText("planned_take_profit_type", event.target.value)}
            >
              <option value="">未填写</option>
              <option value="fixed_price">固定价</option>
              <option value="prior_high">前高</option>
              <option value="rr_multiple">盈亏比</option>
              <option value="trailing_exit">跟随退出</option>
            </select>
          </label>
          <label>
            计划止盈价
            <Input
              aria-label={`trade-intent-${trade.id}-take-profit-value`}
              inputMode="decimal"
              value={draft.planned_take_profit_value ?? ""}
              onChange={(event) => updateText("planned_take_profit_value", event.target.value)}
            />
          </label>
        </div>

        <Space wrap>
          <Button
            type="primary"
            size="small"
            loading={saving}
            aria-label={`trade-intent-save-${trade.id}`}
            onClick={() => void onSave(trade.id, sanitizeIntentSnapshot(draft))}
          >
            保存标签
          </Button>
          {hasAnyValue && trade.intent_snapshot ? (
            <Space wrap>
              {[
                ...trade.intent_snapshot.setup_tags,
                ...trade.intent_snapshot.market_context_tags,
                ...trade.intent_snapshot.security_quality_tags,
                ...trade.intent_snapshot.execution_emotion_tags,
              ]
                .slice(0, 4)
                .map((value) => (
                  <Tag key={`${trade.id}-${value}`}>{tradeIntentTagLabel(value)}</Tag>
                ))}
            </Space>
          ) : null}
        </Space>
      </div>
    </details>
  );
}
