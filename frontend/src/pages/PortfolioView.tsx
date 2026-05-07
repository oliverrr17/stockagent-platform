import {
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  LineChartOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  createCashFlow,
  createManualPosition,
  deletePosition,
  fetchHKTradeHistory,
  fetchPortfolioDailyContributions,
  fetchPortfolioDashboard,
  updatePosition,
} from "../api/portfolio";
import { useApiSettings } from "../context/ApiSettingsContext";
import type {
  CashAccount,
  CashFlow,
  CashFlowPayload,
  PortfolioDailyContributionResponse,
  PortfolioOverview,
  PortfolioPositionAnalytics,
  Position,
  PositionEntryPayload,
  TradeRecord,
} from "../types";
import {
  directionMeta,
  formatDateTime,
  marketMeta,
  positionOriginMeta,
  positionStatusMeta,
  sourceLabel,
} from "../utils/display";
import { getApiErrorMessage } from "../utils/errors";

const { Title, Text } = Typography;

function formatMoney(value: string | number) {
  return Number(value).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function metricClass(value: string | number) {
  const numeric = Number(value);
  if (numeric > 0) return "metric-positive";
  if (numeric < 0) return "metric-negative";
  return "metric-neutral";
}

export function PortfolioView() {
  const {
    settings: { token },
  } = useApiSettings();
  const navigate = useNavigate();
  const [positions, setPositions] = useState<Position[]>([]);
  const [positionAnalytics, setPositionAnalytics] = useState<PortfolioPositionAnalytics[]>([]);
  const [overview, setOverview] = useState<PortfolioOverview | null>(null);
  const [cashAccounts, setCashAccounts] = useState<CashAccount[]>([]);
  const [cashFlows, setCashFlows] = useState<CashFlow[]>([]);
  const [curveMode, setCurveMode] = useState<"daily" | "monthly" | "yearly">("daily");
  const [selectedStockCode, setSelectedStockCode] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [entryOpen, setEntryOpen] = useState(false);
  const [editingPosition, setEditingPosition] = useState<Position | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyRows, setHistoryRows] = useState<TradeRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyCode, setHistoryCode] = useState<string>("");
  const [contributionOpen, setContributionOpen] = useState(false);
  const [contributionLoading, setContributionLoading] = useState(false);
  const [dailyContribution, setDailyContribution] = useState<PortfolioDailyContributionResponse | null>(null);
  const [positionForm] = Form.useForm();
  const [cashFlowForm] = Form.useForm();

  const loadPortfolio = async () => {
    setLoading(true);
    try {
      if (!token) {
        setPositions([]);
        setPositionAnalytics([]);
        setOverview(null);
        setCashAccounts([]);
        setCashFlows([]);
        return;
      }

      const dashboard = await fetchPortfolioDashboard();

      setPositions(dashboard.positions);
      setPositionAnalytics(dashboard.position_analytics);
      setOverview(dashboard.overview);
      setCashAccounts(dashboard.cash_accounts);
      setCashFlows(dashboard.cash_flows);
      if (!selectedStockCode && dashboard.position_analytics.length) {
        setSelectedStockCode(dashboard.position_analytics[0].stock_code);
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, "持仓数据加载失败。"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPortfolio();
  }, [token]);

  const analyticsByCode = useMemo(
    () => Object.fromEntries(positionAnalytics.map((item) => [item.stock_code, item])),
    [positionAnalytics],
  );

  const selectedPositionAnalytics =
    positionAnalytics.find((item) => item.stock_code === selectedStockCode) ?? positionAnalytics[0] ?? null;

  const mergedRows = positions.map((position) => ({
    position,
    analytics: analyticsByCode[position.stock_code],
  }));

  const aShareRows = mergedRows.filter((item) => item.position.market === "A_STOCK");
  const hkRows = mergedRows.filter((item) => item.position.market === "HK_STOCK");

  const openEntryModal = (position?: Position) => {
    setEditingPosition(position ?? null);
    positionForm.setFieldsValue(
      position
        ? {
            market: position.market,
            stock_code: position.stock_code,
            stock_name: position.stock_name,
            quantity: position.quantity,
            cost_price: Number(position.weighted_avg_cost),
            entry_time: dayjs(),
          }
        : {
            market: "HK_STOCK",
            entry_time: dayjs(),
          },
    );
    setEntryOpen(true);
  };

  const submitManualEntry = async () => {
    const values = await positionForm.validateFields();
    const payload: PositionEntryPayload = {
      stock_code: String(values.stock_code).trim().toUpperCase(),
      stock_name: String(values.stock_name).trim(),
      market: values.market,
      quantity: Number(values.quantity),
      cost_price: Number(values.cost_price).toFixed(4),
      entry_time: values.entry_time.toISOString(),
    };

    try {
      if (editingPosition) {
        await updatePosition(editingPosition.id, payload);
        message.success("持仓更新成功。");
      } else {
        await createManualPosition(payload);
        message.success("持仓录入成功。");
      }
      setEntryOpen(false);
      setEditingPosition(null);
      positionForm.resetFields();
      await loadPortfolio();
    } catch (error) {
      message.error(getApiErrorMessage(error, "手动录入失败。"));
    }
  };

  const submitCashFlow = async () => {
    const values = await cashFlowForm.validateFields();
    const payload: CashFlowPayload = {
      currency: values.currency,
      direction: values.direction,
      amount: Number(values.amount).toFixed(4),
      occurred_at: values.occurred_at.toISOString(),
      note: values.note || "",
    };

    try {
      await createCashFlow(payload);
      message.success("现金流水已录入。");
      cashFlowForm.resetFields();
      cashFlowForm.setFieldsValue({ currency: "CNY", direction: "DEPOSIT", occurred_at: dayjs() });
      await loadPortfolio();
    } catch (error) {
      message.error(getApiErrorMessage(error, "现金流水录入失败。"));
    }
  };

  const handleDelete = async (position: Position) => {
    try {
      await deletePosition(position.id);
      message.success("持仓已删除。");
      await loadPortfolio();
    } catch (error) {
      message.error(getApiErrorMessage(error, "持仓删除失败。"));
    }
  };

  const currentPositionColumns: ColumnsType<{ position: Position; analytics?: PortfolioPositionAnalytics }> = [
    {
      title: "证券",
      key: "stock",
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.position.stock_code}</Text>
          <Text type="secondary">{record.position.stock_name}</Text>
        </Space>
      ),
    },
    {
      title: "市场",
      key: "market",
      render: (_, record) => <Tag color={marketMeta(record.position.market).color}>{marketMeta(record.position.market).label}</Tag>,
    },
    {
      title: "来源",
      key: "origin",
      render: (_, record) => <Tag color={positionOriginMeta(record.position.origin).color}>{positionOriginMeta(record.position.origin).label}</Tag>,
    },
    { title: "数量", dataIndex: ["position", "quantity"], key: "quantity", align: "right" },
    {
      title: "最新价",
      key: "latest_price",
      align: "right",
      render: (_, record) => formatMoney(record.analytics?.latest_price ?? record.position.weighted_avg_cost),
    },
    {
      title: "未实现收益",
      key: "unrealized_pnl_cny",
      align: "right",
      render: (_, record) => (
        <span className={metricClass(record.analytics?.unrealized_pnl_cny ?? 0)}>
          {formatMoney(record.analytics?.unrealized_pnl_cny ?? 0)}
        </span>
      ),
    },
    {
      title: "日收益",
      key: "daily_pnl_cny",
      align: "right",
      render: (_, record) => (
        <span className={metricClass(record.analytics?.daily_pnl_cny ?? 0)}>
          {formatMoney(record.analytics?.daily_pnl_cny ?? 0)}
        </span>
      ),
    },
    {
      title: "操作",
      key: "action",
      render: (_, record) => (
        <Space wrap>
          {record.position.market === "HK_STOCK" ? (
            <Button
              icon={<HistoryOutlined />}
              onClick={async () => {
                setHistoryOpen(true);
                setHistoryCode(record.position.stock_code);
                setHistoryLoading(true);
                try {
                  const rows = await fetchHKTradeHistory(record.position.stock_code);
                  setHistoryRows(rows);
                } catch (error) {
                  message.error(getApiErrorMessage(error, "交易历史加载失败。"));
                } finally {
                  setHistoryLoading(false);
                }
              }}
            >
              历史
            </Button>
          ) : null}
          {record.position.origin === "MANUAL" ? (
            <>
              <Button icon={<EditOutlined />} onClick={() => openEntryModal(record.position)}>
                编辑
              </Button>
              <Popconfirm title="确认删除这条持仓吗？" onConfirm={() => void handleDelete(record.position)}>
                <Button danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            </>
          ) : (
            <Text type="secondary">自动同步项仅可通过同步更新</Text>
          )}
        </Space>
      ),
    },
  ];

  const historyColumns: ColumnsType<TradeRecord> = [
    {
      title: "方向",
      dataIndex: "direction",
      key: "direction",
      render: (value) => <Tag color={directionMeta(value).color}>{directionMeta(value).label}</Tag>,
    },
    { title: "价格", dataIndex: "price", key: "price", render: (value) => formatMoney(value) },
    { title: "数量", dataIndex: "quantity", key: "quantity" },
    {
      title: "交易时间",
      dataIndex: "trade_time",
      key: "trade_time",
      render: (value) => formatDateTime(value),
    },
    { title: "来源", dataIndex: "source", key: "source", render: (value) => sourceLabel(value) },
  ];

  const curveData = overview?.curves[curveMode] ?? [];
  const valuationDate =
    overview?.valuation_date ?? (overview?.curves.daily.length ? overview.curves.daily[overview.curves.daily.length - 1].date : "");

  const loadDailyContribution = async () => {
    if (!valuationDate) {
      return;
    }
    setContributionLoading(true);
    try {
      const payload = await fetchPortfolioDailyContributions(valuationDate);
      setDailyContribution(payload);
      setContributionOpen(true);
    } catch (error) {
      message.error(getApiErrorMessage(error, "当日收益明细加载失败。"));
    } finally {
      setContributionLoading(false);
    }
  };

  const contributionColumns: ColumnsType<NonNullable<PortfolioDailyContributionResponse["contributions"]>[number]> = [
    {
      title: "证券",
      key: "stock",
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.stock_code}</Text>
          <Text type="secondary">{record.stock_name}</Text>
        </Space>
      ),
    },
    {
      title: "市场",
      dataIndex: "market",
      key: "market",
      render: (value) => <Tag color={marketMeta(value).color}>{marketMeta(value).label}</Tag>,
    },
    {
      title: "日收益(CNY)",
      dataIndex: "daily_pnl_cny",
      key: "daily_pnl_cny",
      align: "right",
      render: (value) => <span className={metricClass(value)}>{formatMoney(value)}</span>,
    },
    {
      title: "价格源",
      dataIndex: "price_source",
      key: "price_source",
    },
    {
      title: "审计状态",
      dataIndex: "audit_status",
      key: "audit_status",
      render: (value) => <Tag color={value === "FINAL" ? "green" : "orange"}>{value}</Tag>,
    },
  ];

  return (
    <div className="page-shell portfolio-grid">
      <div className="page-header">
        <div>
          <Title className="page-title">持仓与收益</Title>
          <Text className="page-description">以人民币为统一口径查看双币种现金、组合收益曲线和个股盈亏。</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void loadPortfolio()} loading={loading}>
            刷新
          </Button>
          <Button icon={<LineChartOutlined />} onClick={() => navigate("/portfolio/cleared")}>
            已清仓股票
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openEntryModal()}>
            手动录入
          </Button>
        </Space>
      </div>

      <div className="stats-grid">
        {[
          { label: "总资产(CNY)", value: formatMoney(overview?.total_assets_cny ?? 0) },
          { label: "总收益(CNY)", value: formatMoney(overview?.total_return_cny ?? 0) },
          { label: "已实现收益(CNY)", value: formatMoney(overview?.realized_pnl_cny ?? 0) },
          { label: "未实现收益(CNY)", value: formatMoney(overview?.unrealized_pnl_cny ?? 0) },
          { label: "日收益率", value: `${Number(overview?.returns.daily ?? 0).toFixed(2)}%` },
          { label: "月收益率", value: `${Number(overview?.returns.monthly ?? 0).toFixed(2)}%` },
          { label: "年收益率", value: `${Number(overview?.returns.yearly ?? 0).toFixed(2)}%` },
        ].map((item) => (
          <div key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <span className="stat-value">{item.value}</span>
          </div>
        ))}
      </div>

      {overview ? (
        <Card className="surface-card section-card" variant="borderless">
          <Space wrap align="center">
            <Text strong>收益对应日期</Text>
            <Tag>{valuationDate || "--"}</Tag>
            <Text strong>审计状态</Text>
            <Tag color={overview.audit_status === "FINAL" ? "green" : "orange"}>{overview.audit_status ?? "PROVISIONAL"}</Tag>
            <Button onClick={() => void loadDailyContribution()} loading={contributionLoading}>
              查看当日收益明细
            </Button>
          </Space>
        </Card>
      ) : null}

      <Card className="surface-card section-card" variant="borderless">
        <div className="section-head">
          <div>
            <Title level={4} className="section-title">
              整体收益曲线
            </Title>
            <Text type="secondary">收益率采用 TWR 口径，图表显示总资产与累计收益率。</Text>
          </div>
          <Segmented
            value={curveMode}
            onChange={(value) => setCurveMode(value as "daily" | "monthly" | "yearly")}
            options={[
              { label: "日", value: "daily" },
              { label: "月", value: "monthly" },
              { label: "年", value: "yearly" },
            ]}
          />
        </div>
        <div className="chart-shell">
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={curveData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(17,100,102,0.12)" />
              <XAxis dataKey="date" />
              <YAxis yAxisId="assets" tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} />
              <YAxis yAxisId="return" orientation="right" tickFormatter={(value) => `${Number(value).toFixed(1)}%`} />
              <Tooltip
                formatter={(value, name) => {
                  if (name === "总资产") return [formatMoney(Number(value)), name];
                  return [`${Number(value).toFixed(2)}%`, name];
                }}
              />
              <Line yAxisId="assets" type="monotone" dataKey="total_assets_cny" name="总资产" stroke="#116466" strokeWidth={2.5} dot={false} />
              <Line yAxisId="return" type="monotone" dataKey="cumulative_return_pct" name="累计收益率" stroke="#a45f2a" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="split-grid">
        <Card className="surface-card section-card a-share-band" variant="borderless">
          <div className="section-head">
            <div>
              <Title level={4} className="section-title">
                A股持仓
              </Title>
            </div>
          </div>
          <Table
            size="small"
            rowKey={(record) => record.position.id}
            loading={loading}
            columns={currentPositionColumns}
            dataSource={aShareRows}
            pagination={false}
            onRow={(record) => ({
              onClick: () => setSelectedStockCode(record.position.stock_code),
            })}
            rowClassName={(record) => (record.position.stock_code === selectedStockCode ? "table-row-selected" : "")}
            locale={{ emptyText: <div className="empty-note">暂无活跃 A 股持仓。</div> }}
          />
        </Card>

        <Card className="surface-card section-card hk-band" variant="borderless">
          <div className="section-head">
            <div>
              <Title level={4} className="section-title">
                港股持仓
              </Title>
            </div>
          </div>
          <Table
            size="small"
            rowKey={(record) => record.position.id}
            loading={loading}
            columns={currentPositionColumns}
            dataSource={hkRows}
            pagination={false}
            onRow={(record) => ({
              onClick: () => setSelectedStockCode(record.position.stock_code),
            })}
            rowClassName={(record) => (record.position.stock_code === selectedStockCode ? "table-row-selected" : "")}
            locale={{ emptyText: <div className="empty-note">暂无活跃港股持仓。</div> }}
          />
        </Card>
      </div>

      <Card className="surface-card section-card" variant="borderless">
        <div className="section-head">
          <div>
            <Title level={4} className="section-title">
              个股盈亏
            </Title>
            <Text type="secondary">点击上方任一持仓行后，在这里查看该股票的盈亏情况。</Text>
          </div>
        </div>
        {selectedPositionAnalytics ? (
          <>
            <Space wrap>
              <Tag color={selectedPositionAnalytics.degraded ? "orange" : "green"}>
                {selectedPositionAnalytics.degraded ? "行情回退" : "真实行情"}
              </Tag>
              <Tag>数据源：{selectedPositionAnalytics.data_source}</Tag>
            </Space>
            {selectedPositionAnalytics.degraded ? (
              <Alert
                className="portfolio-inline-alert"
                type="warning"
                showIcon
                message="当前股票未使用实时行情"
                description={selectedPositionAnalytics.degraded_reason || "当前无真实行情，已回退为成本价估算。"}
              />
            ) : null}
            <div className="stats-grid portfolio-mini-stats">
              {[
                { label: "股票", value: `${selectedPositionAnalytics.stock_code}` },
                { label: "最新价", value: formatMoney(selectedPositionAnalytics.latest_price) },
                { label: "昨收", value: formatMoney(selectedPositionAnalytics.previous_close) },
                { label: "市值(CNY)", value: formatMoney(selectedPositionAnalytics.market_value_cny) },
                { label: "未实现(CNY)", value: formatMoney(selectedPositionAnalytics.unrealized_pnl_cny) },
                { label: "日收益(CNY)", value: formatMoney(selectedPositionAnalytics.daily_pnl_cny) },
                { label: "收益率", value: `${selectedPositionAnalytics.return_pct.toFixed(2)}%` },
              ].map((item) => (
                <div key={item.label} className="stat-card">
                  <span className="stat-label">{item.label}</span>
                  <span className="stat-value">{item.value}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="empty-note">请先点击一只持仓股票。</div>
        )}
      </Card>

      <Card className="surface-card section-card" variant="borderless">
        <div className="section-head">
          <div>
            <Title level={4} className="section-title">
              现金账户
            </Title>
            <Text type="secondary">人民币和港币现金分别管理，统一按人民币结算。</Text>
          </div>
        </div>
        <div className="ops-summary-grid">
          {cashAccounts.map((account) => (
            <div key={account.id} className="ops-pill">
              <span>{account.currency}</span>
              <strong>{formatMoney(account.balance)}</strong>
            </div>
          ))}
          {overview ? (
            <div className="ops-pill">
              <span>HKD 折算</span>
              <strong>{formatMoney(overview.cash_balances.HKD.balance_cny)}</strong>
            </div>
          ) : null}
        </div>
        <div className="section-head portfolio-subsection-head">
          <div>
            <Title level={5} className="section-title">
              录入现金流水
            </Title>
          </div>
        </div>
        <Form
          form={cashFlowForm}
          layout="vertical"
          initialValues={{ currency: "CNY", direction: "DEPOSIT", occurred_at: dayjs() }}
        >
          <div className="filter-row">
            <Form.Item label="币种" name="currency" rules={[{ required: true }]}>
              <Select
                options={[
                  { label: "人民币", value: "CNY" },
                  { label: "港币", value: "HKD" },
                ]}
              />
            </Form.Item>
            <Form.Item label="方向" name="direction" rules={[{ required: true }]}>
              <Select
                options={[
                  { label: "入金", value: "DEPOSIT" },
                  { label: "出金", value: "WITHDRAWAL" },
                ]}
              />
            </Form.Item>
            <Form.Item label="金额" name="amount" rules={[{ required: true }]}>
              <InputNumber min={0} step={0.01} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item label="时间" name="occurred_at" rules={[{ required: true }]}>
              <DatePicker showTime style={{ width: "100%" }} />
            </Form.Item>
          </div>
          <Form.Item label="备注" name="note">
            <Input placeholder="例如：期初现金、追加资金、取现" />
          </Form.Item>
          <Button type="primary" onClick={() => void submitCashFlow()}>
            保存现金流水
          </Button>
        </Form>
      </Card>

      <Card className="surface-card section-card" variant="borderless">
        <div className="section-head">
          <div>
            <Title level={4} className="section-title">
              最近现金流水
            </Title>
            <Text type="secondary">从今天开始记录账户级入金和出金。</Text>
          </div>
        </div>
        <Table
          size="small"
          rowKey="id"
          dataSource={cashFlows.slice(0, 12)}
          pagination={false}
          columns={[
            { title: "币种", dataIndex: "currency", key: "currency" },
            {
              title: "方向",
              dataIndex: "direction",
              key: "direction",
              render: (value) => <Tag color={value === "DEPOSIT" ? "green" : "volcano"}>{value === "DEPOSIT" ? "入金" : "出金"}</Tag>,
            },
            { title: "金额", dataIndex: "amount", key: "amount", render: (value) => formatMoney(value) },
            { title: "时间", dataIndex: "occurred_at", key: "occurred_at", render: (value) => formatDateTime(value) },
            { title: "备注", dataIndex: "note", key: "note" },
          ]}
          locale={{ emptyText: <div className="empty-note">暂无现金流水。</div> }}
        />
      </Card>

      <Modal
        open={entryOpen}
        onCancel={() => {
          setEntryOpen(false);
          setEditingPosition(null);
        }}
        onOk={() => void submitManualEntry()}
        okText={editingPosition ? "确认更新" : "确认录入"}
        title={editingPosition ? "编辑持仓" : "手动录入持仓"}
        destroyOnHidden
      >
        <Form form={positionForm} layout="vertical">
          <Form.Item label="市场" name="market" rules={[{ required: true, message: "请选择市场。" }]}>
            <Segmented
              block
              options={[
                { label: "港股", value: "HK_STOCK" },
                { label: "A股", value: "A_STOCK" },
              ]}
            />
          </Form.Item>
          <Form.Item label="股票代码" name="stock_code" rules={[{ required: true, message: "请输入股票代码。" }]}>
            <Input placeholder="例如 02610 或 603063" />
          </Form.Item>
          <Form.Item label="股票名称" name="stock_name" rules={[{ required: true, message: "请输入股票名称。" }]}>
            <Input placeholder="输入股票名称" />
          </Form.Item>
          <Form.Item label="数量" name="quantity" rules={[{ required: true, message: "请输入数量。" }]}>
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item label="成本价" name="cost_price" rules={[{ required: true, message: "请输入成本价。" }]}>
            <InputNumber min={0} step={0.01} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item label="录入时间" name="entry_time" rules={[{ required: true, message: "请选择录入时间。" }]}>
            <DatePicker showTime style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={`交易历史 · ${historyCode || "--"}`}
        width={720}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        className="history-drawer"
      >
        <Table
          size="small"
          rowKey="id"
          loading={historyLoading}
          columns={historyColumns}
          dataSource={historyRows}
          pagination={{ pageSize: 6, showSizeChanger: false }}
        />
      </Drawer>

      <Drawer
        title={`当日收益明细 · ${dailyContribution?.snapshot_date ?? valuationDate ?? "--"}`}
        width={860}
        open={contributionOpen}
        onClose={() => setContributionOpen(false)}
      >
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Space wrap>
            <Tag color={dailyContribution?.audit_status === "FINAL" ? "green" : "orange"}>
              {dailyContribution?.audit_status ?? overview?.audit_status ?? "PROVISIONAL"}
            </Tag>
            <Text>组合日收益：{formatMoney(dailyContribution?.computed_daily_pnl_cny ?? 0)}</Text>
            <Text>外部资金流：{formatMoney(dailyContribution?.external_flow_cny ?? 0)}</Text>
          </Space>
          <Table
            size="small"
            rowKey={(record) => `${record.market}-${record.stock_code}`}
            loading={contributionLoading}
            columns={contributionColumns}
            dataSource={dailyContribution?.contributions ?? []}
            pagination={false}
          />
        </Space>
      </Drawer>
    </div>
  );
}
