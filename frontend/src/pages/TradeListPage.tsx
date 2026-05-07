import { PlusOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Card, Input, Modal, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useDeferredValue, useEffect, useState } from "react";
import { TradeIntentInlineEditor } from "../components/TradeIntentInlineEditor";
import { createTrade, fetchTrades, updateTradeIntentSnapshot } from "../api/trades";
import { useApiSettings } from "../context/ApiSettingsContext";
import type { TradeCreatePayload, TradeDirection, TradeIntentSnapshot, TradeMarket, TradeRecord } from "../types";
import { directionMeta, marketMeta, sourceLabel, summarizeIntentTags } from "../utils/display";
import { getApiErrorMessage } from "../utils/errors";

const { Title, Text } = Typography;

type ManualTradeFormState = {
  stock_code: string;
  stock_name: string;
  market: TradeMarket;
  direction: TradeDirection;
  price: string;
  quantity: string;
  trade_time: string;
};

const DEFAULT_FORM_STATE: ManualTradeFormState = {
  stock_code: "",
  stock_name: "",
  market: "A_STOCK",
  direction: "BUY",
  price: "",
  quantity: "",
  trade_time: "",
};

function numberText(value: string | number) {
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}

function toOffsetDateTime(value: string) {
  const match = value.match(
    /^(?<year>\d{4})-(?<month>\d{2})-(?<day>\d{2})T(?<hour>\d{2}):(?<minute>\d{2})(?::(?<second>\d{2})(?:\.\d+)?)?$/,
  );
  if (!match?.groups) {
    return value;
  }

  const { year, month, day, hour, minute, second = "00" } = match.groups;
  const local = new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second));
  const offsetMinutes = -local.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absoluteMinutes = Math.abs(offsetMinutes);
  const offsetHour = String(Math.floor(absoluteMinutes / 60)).padStart(2, "0");
  const offsetMinute = String(absoluteMinutes % 60).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}:${second}${sign}${offsetHour}:${offsetMinute}`;
}

function buildManualTradePayload(formState: ManualTradeFormState): TradeCreatePayload {
  return {
    stock_code: formState.stock_code.trim().toUpperCase(),
    stock_name: formState.stock_name.trim(),
    market: formState.market,
    direction: formState.direction,
    price: Number(formState.price).toFixed(4),
    quantity: Number.parseInt(formState.quantity, 10),
    trade_time: toOffsetDateTime(formState.trade_time),
    source: "MANUAL",
    commission: "0",
    stamp_duty: "0",
    other_fees: "0",
  };
}

export function TradeListPage() {
  const {
    settings: { token },
  } = useApiSettings();
  const [market, setMarket] = useState<string | undefined>();
  const [direction, setDirection] = useState<string | undefined>();
  const [stockCodeInput, setStockCodeInput] = useState("");
  const deferredStockCode = useDeferredValue(stockCodeInput.trim().toUpperCase());
  const [rows, setRows] = useState<TradeRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [manualModalOpen, setManualModalOpen] = useState(false);
  const [savingManualTrade, setSavingManualTrade] = useState(false);
  const [savingIntentTradeId, setSavingIntentTradeId] = useState<number | null>(null);
  const [manualForm, setManualForm] = useState<ManualTradeFormState>(DEFAULT_FORM_STATE);

  const loadTrades = async () => {
    setLoading(true);
    try {
      if (!token) {
        setRows([]);
        return;
      }
      const data = await fetchTrades({
        market,
        direction,
        stock_code: deferredStockCode || undefined,
        ordering: "-trade_time",
      });
      setRows(data);
    } catch (error) {
      message.error(getApiErrorMessage(error, "交易记录加载失败。"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadTrades();
  }, [market, direction, deferredStockCode, token]);

  const updateManualForm = (field: keyof ManualTradeFormState, value: string) => {
    setManualForm((current) => ({ ...current, [field]: value }));
  };

  const resetManualForm = () => {
    setManualForm(DEFAULT_FORM_STATE);
  };

  const submitManualTrade = async () => {
    const payload = buildManualTradePayload(manualForm);
    if (
      !payload.stock_code ||
      !payload.stock_name ||
      !payload.trade_time ||
      !Number.isFinite(Number(manualForm.price)) ||
      !Number.isInteger(payload.quantity) ||
      payload.quantity <= 0
    ) {
      message.error("请完整填写手动交易信息。");
      return;
    }

    setSavingManualTrade(true);
    try {
      await createTrade(payload);
      message.success("手动交易已录入。");
      setManualModalOpen(false);
      resetManualForm();
      await loadTrades();
    } catch (error) {
      message.error(getApiErrorMessage(error, "手动交易录入失败。"));
    } finally {
      setSavingManualTrade(false);
    }
  };

  const handleIntentSave = async (tradeId: number, intentSnapshot: TradeIntentSnapshot) => {
    setSavingIntentTradeId(tradeId);
    try {
      const updated = await updateTradeIntentSnapshot(tradeId, intentSnapshot);
      setRows((current) => current.map((row) => (row.id === tradeId ? updated : row)));
      message.success("交易意图已保存。");
    } catch (error) {
      message.error(getApiErrorMessage(error, "交易意图保存失败。"));
    } finally {
      setSavingIntentTradeId((current) => (current === tradeId ? null : current));
    }
  };

  const columns: ColumnsType<TradeRecord> = [
    {
      title: "代码",
      dataIndex: "stock_code",
      key: "stock_code",
      render: (value, record) => {
        const intentTags = summarizeIntentTags(record.intent_snapshot).slice(0, 3);
        return (
          <Space direction="vertical" size={0}>
            <Text strong>{value}</Text>
            <Text type="secondary">{record.stock_name}</Text>
            {intentTags.length ? <Text type="secondary">{intentTags.join(" · ")}</Text> : null}
          </Space>
        );
      },
    },
    {
      title: "市场",
      dataIndex: "market",
      key: "market",
      render: (value) => {
        const meta = marketMeta(value);
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "方向",
      dataIndex: "direction",
      key: "direction",
      render: (value) => {
        const meta = directionMeta(value);
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "价格",
      dataIndex: "price",
      key: "price",
      align: "right",
      render: (value) => numberText(value),
    },
    {
      title: "数量",
      dataIndex: "quantity",
      key: "quantity",
      align: "right",
      render: (value) => numberText(value),
    },
    {
      title: "时间",
      dataIndex: "trade_time",
      key: "trade_time",
      render: (value) => new Date(value).toLocaleString("zh-CN"),
    },
    {
      title: "来源",
      dataIndex: "source",
      key: "source",
      render: (value) => <Tag>{sourceLabel(value)}</Tag>,
    },
    {
      title: "意图标签",
      key: "intent_editor",
      render: (_, record) => (
        <TradeIntentInlineEditor
          trade={record}
          saving={savingIntentTradeId === record.id}
          onSave={handleIntentSave}
        />
      ),
    },
  ];

  const buyCount = rows.filter((item) => item.direction === "BUY").length;
  const sellCount = rows.filter((item) => item.direction === "SELL").length;
  const turnover = rows.reduce((sum, item) => sum + Number(item.price) * item.quantity, 0);
  const stats = [
    { label: "当前结果数", value: rows.length.toString() },
    { label: "买入笔数", value: buyCount.toString() },
    { label: "卖出笔数", value: sellCount.toString() },
    { label: "成交额", value: turnover.toLocaleString("zh-CN", { maximumFractionDigits: 2 }) },
  ];

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <Title className="page-title">交易记录</Title>
          <Text className="page-description">查看来自 THS 与 HSBC 链路的交易，交易落库后可在每行末尾补充交易前意图。</Text>
        </div>
        <Space wrap>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            aria-label="manual-trade-open"
            disabled={!token}
            onClick={() => setManualModalOpen(true)}
          >
            手动录入
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => void loadTrades()} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      <div className="stats-grid">
        {stats.map((item) => (
          <div key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <span className="stat-value">{item.value}</span>
          </div>
        ))}
      </div>

      <Card className="surface-card section-card" variant="borderless">
        <div className="section-head">
          <div>
            <Title level={4} className="section-title">筛选条件</Title>
            <Text type="secondary">在当前页面内直接筛选交易记录。</Text>
          </div>
        </div>
        <div className="filter-row">
          <select
            aria-label="trade-market-filter"
            value={market ?? ""}
            onChange={(event) => setMarket(event.target.value || undefined)}
          >
            <option value="">市场</option>
            <option value="A_STOCK">A股</option>
            <option value="HK_STOCK">港股</option>
          </select>
          <select
            aria-label="trade-direction-filter"
            value={direction ?? ""}
            onChange={(event) => setDirection(event.target.value || undefined)}
          >
            <option value="">方向</option>
            <option value="BUY">买入</option>
            <option value="SELL">卖出</option>
          </select>
          <Input
            placeholder="按股票代码筛选"
            prefix={<SearchOutlined />}
            value={stockCodeInput}
            onChange={(event) => setStockCodeInput(event.target.value)}
          />
        </div>
      </Card>

      {!token ? (
        <Card className="surface-card section-card" variant="borderless">
          <div className="empty-note">请先在“接口访问”抽屉中保存 JWT，才能加载真实交易数据。</div>
        </Card>
      ) : null}

      <Card className="surface-card section-card table-card" variant="borderless">
        <div className="section-head">
          <div>
            <Title level={4} className="section-title">当前结果集</Title>
            <Text type="secondary">按最新交易时间倒序展示。</Text>
          </div>
        </div>
        <Table
          size="small"
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          locale={{ emptyText: <div className="empty-note">没有符合当前筛选条件的交易记录。</div> }}
        />
      </Card>

      <Modal
        title="手动录入交易"
        open={manualModalOpen}
        destroyOnHidden
        onCancel={() => {
          setManualModalOpen(false);
          resetManualForm();
        }}
        footer={null}
      >
        <div className="manual-trade-form">
          <label>
            股票代码
            <Input
              aria-label="manual-stock-code"
              value={manualForm.stock_code}
              onChange={(event) => updateManualForm("stock_code", event.target.value)}
            />
          </label>
          <label>
            股票名称
            <Input
              aria-label="manual-stock-name"
              value={manualForm.stock_name}
              onChange={(event) => updateManualForm("stock_name", event.target.value)}
            />
          </label>
          <label>
            市场
            <select
              aria-label="manual-market"
              value={manualForm.market}
              onChange={(event) => updateManualForm("market", event.target.value)}
            >
              <option value="A_STOCK">A股</option>
              <option value="HK_STOCK">港股</option>
            </select>
          </label>
          <label>
            买卖方向
            <select
              aria-label="manual-direction"
              value={manualForm.direction}
              onChange={(event) => updateManualForm("direction", event.target.value)}
            >
              <option value="BUY">买入</option>
              <option value="SELL">卖出</option>
            </select>
          </label>
          <label>
            成交价
            <Input
              aria-label="manual-price"
              inputMode="decimal"
              value={manualForm.price}
              onChange={(event) => updateManualForm("price", event.target.value)}
            />
          </label>
          <label>
            股数
            <Input
              aria-label="manual-quantity"
              inputMode="numeric"
              value={manualForm.quantity}
              onChange={(event) => updateManualForm("quantity", event.target.value)}
            />
          </label>
          <label>
            成交时间
            <Input
              aria-label="manual-trade-time"
              type="datetime-local"
              step={1}
              value={manualForm.trade_time}
              onChange={(event) => updateManualForm("trade_time", event.target.value)}
            />
          </label>
          <Space>
            <Button
              onClick={() => {
                setManualModalOpen(false);
                resetManualForm();
              }}
            >
              取消
            </Button>
            <Button
              type="primary"
              loading={savingManualTrade}
              aria-label="manual-trade-submit"
              onClick={() => void submitManualTrade()}
            >
              保存
            </Button>
          </Space>
        </div>
      </Modal>
    </div>
  );
}
