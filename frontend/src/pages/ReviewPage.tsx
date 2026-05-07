import {
  CalculatorOutlined,
  CheckCircleOutlined,
  HistoryOutlined,
  RadarChartOutlined,
  ReloadOutlined,
  RiseOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Empty, List, Select, Space, Statistic, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchReviewReports, generateReviewReport } from "../api/analysis";
import { fetchTrades } from "../api/trades";
import { AnalysisDataStatus } from "../components/AnalysisDataStatus";
import { ReviewPriceCandlestickChart } from "../components/ReviewPriceCandlestickChart";
import { useApiSettings } from "../context/ApiSettingsContext";
import type { ReviewReport, TradeIntentSnapshot, TradeRecord } from "../types";
import { directionMeta, formatDateTime, marketMeta, normalizeTradeIntentSnapshot, sourceLabel, summarizeIntentTags, tradeIntentTagLabel } from "../utils/display";
import { getApiErrorMessage } from "../utils/errors";
import { extractReviewMetricEntries } from "../utils/review";
import type { PriceChartPoint } from "../utils/reviewCharts";
import { hasCandlestickData } from "../utils/reviewCharts";

const { Title, Text, Paragraph } = Typography;

type VolumeChartPoint = {
  trade_date: string;
  volume: number;
  avg_volume_5: number;
  avg_volume_10: number;
  avg_volume_20: number;
};

function tradeLabel(trade: TradeRecord) {
  const direction = directionMeta(trade.direction).label;
  return `${trade.stock_code} · ${trade.stock_name} · ${direction}`;
}

function formatChartDate(value: string) {
  if (!value) return "";
  if (value.includes("-")) return value.slice(5);
  if (value.length === 8) return `${value.slice(4, 6)}-${value.slice(6)}`;
  return value;
}

function renderIntentBlock(snapshot: TradeIntentSnapshot | null | undefined) {
  const normalizedSnapshot = normalizeTradeIntentSnapshot(snapshot);
  if (!normalizedSnapshot) {
    return <Text type="secondary">当前交易没有保存交易前意图快照。</Text>;
  }

  const groups = [
    { label: "Setup", values: normalizedSnapshot.setup_tags },
    { label: "市场环境", values: normalizedSnapshot.market_context_tags },
    { label: "标的质量", values: normalizedSnapshot.security_quality_tags },
    { label: "执行与情绪", values: normalizedSnapshot.execution_emotion_tags },
  ];

  return (
    <Space direction="vertical" size={10} style={{ width: "100%" }}>
      {groups.map((group) => (
        <div key={group.label}>
          <Text strong>{group.label}</Text>
          <div style={{ marginTop: 6 }}>
            {group.values.length ? (
              group.values.map((value) => (
                <Tag key={`${group.label}-${value}`} color="blue">
                  {tradeIntentTagLabel(value)}
                </Tag>
              ))
            ) : (
              <Text type="secondary">未填写</Text>
            )}
          </div>
        </div>
      ))}

      <div>
        <Text strong>计划字段</Text>
        <Paragraph style={{ marginBottom: 0 }}>
          持有周期：{normalizedSnapshot.planned_holding_period || "未填写"} ｜ 止损：{normalizedSnapshot.planned_stop_loss_type || "未填写"} {normalizedSnapshot.planned_stop_loss_value || ""} ｜ 止盈：{normalizedSnapshot.planned_take_profit_type || "未填写"} {normalizedSnapshot.planned_take_profit_value || ""}
        </Paragraph>
      </div>

      {normalizedSnapshot.overall_notes ? (
        <div>
          <Text strong>整体备注</Text>
          <Paragraph style={{ marginBottom: 0 }}>{normalizedSnapshot.overall_notes}</Paragraph>
        </div>
      ) : null}
    </Space>
  );
}

export function normalizeMissingDataNotes(notes: string[] | string | null | undefined): string[] {
  const NOTE_LABELS: Record<string, string> = {
    intent_snapshot_missing: "交易意图快照缺失，无法对比计划与实际执行。",
    review_llm_not_configured: "LLM 尚未配置，当前报告为本地降级版。",
  };

  const toRawString = (value: unknown): string => {
    return typeof value === "string" ? value : String(value ?? "");
  };

  const normalizeItem = (value: unknown): string => {
    const text = toRawString(value).trim();
    return NOTE_LABELS[text] ?? text;
  };

  const looksFragmented = (items: string[]) => {
    if (items.length < 6) return false;
    const shortCount = items.filter((item) => item.length <= 2).length;
    const compactTokenCount = items.filter((item) => /^[A-Za-z0-9_.:-]+$/.test(item)).length;
    return shortCount >= items.length - 1 || compactTokenCount >= 5;
  };

  if (!notes) return [];

  if (typeof notes === "string") {
    const normalized = normalizeItem(notes);
    return normalized ? [normalized] : [];
  }

  const rawItems = notes.map(toRawString);
  const normalizedItems = rawItems.map(normalizeItem).filter(Boolean);
  if (!normalizedItems.length) return [];
  if (looksFragmented(normalizedItems)) {
    const joined = rawItems.join("").trim();
    return joined ? [joined] : [];
  }
  return normalizedItems;
}

function isLlmFallbackReport(report: ReviewReport | null | undefined): boolean {
  if (!report) return false;
  const notes = normalizeMissingDataNotes(report.coach_report_payload?.missing_data_notes);
  return notes.some((item) => item.includes("review_llm_error:"));
}

function isLegacyEmptyReport(report: ReviewReport | null | undefined): boolean {
  return Boolean(
    report &&
      Object.keys(report.intent_snapshot ?? {}).length === 0 &&
      Object.keys(report.objective_summary ?? {}).length === 0 &&
      Object.keys(report.intent_gap_diagnosis ?? {}).length === 0 &&
      Object.keys(report.subscores ?? {}).length === 0 &&
      Object.keys(report.coach_report_payload ?? {}).length === 0,
  );
}

function reportQualityScore(report: ReviewReport): number {
  let score = 0;
  if (!isLlmFallbackReport(report)) score += 1000;
  if (!isLegacyEmptyReport(report)) score += 200;
  if (report.coach_report_payload?.overall_verdict) score += 100;
  if (report.coach_report_payload?.next_time_rules?.length) score += 30;
  if (report.objective_summary && Object.keys(report.objective_summary).length) score += 20;
  if (report.is_latest) score += 10;
  return score;
}

export function pickPreferredReportId(reports: ReviewReport[]): number | null {
  if (!reports.length) return null;
  const best = reports.reduce<ReviewReport | null>((currentBest, candidate) => {
    if (!currentBest) return candidate;

    const candidateScore = reportQualityScore(candidate);
    const bestScore = reportQualityScore(currentBest);
    if (candidateScore !== bestScore) {
      return candidateScore > bestScore ? candidate : currentBest;
    }

    const candidateCreatedAt = Date.parse(candidate.created_at || "");
    const bestCreatedAt = Date.parse(currentBest.created_at || "");
    if (candidateCreatedAt !== bestCreatedAt) {
      return candidateCreatedAt > bestCreatedAt ? candidate : currentBest;
    }

    return candidate.id > currentBest.id ? candidate : currentBest;
  }, null);

  return best?.id ?? null;
}

export function ReviewPage() {
  const {
    settings: { token },
  } = useApiSettings();
  const [loadingTrades, setLoadingTrades] = useState(false);
  const [loadingReports, setLoadingReports] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [reports, setReports] = useState<ReviewReport[]>([]);
  const [selectedTradeId, setSelectedTradeId] = useState<number | null>(null);
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);

  const selectedTrade = useMemo(
    () => trades.find((item) => item.id === selectedTradeId) ?? null,
    [selectedTradeId, trades],
  );
  const selectedReport = useMemo(
    () => reports.find((item) => item.id === selectedReportId) ?? null,
    [reports, selectedReportId],
  );
  const selectedIntentSnapshot = normalizeTradeIntentSnapshot(
    selectedReport?.trade_intent_snapshot ?? selectedReport?.intent_snapshot ?? selectedTrade?.intent_snapshot ?? null,
  );

  const loadTrades = async () => {
    setLoadingTrades(true);
    try {
      if (!token) {
        setTrades([]);
        return;
      }
      const rows = await fetchTrades({ ordering: "-trade_time" });
      setTrades(rows);
      if (!selectedTradeId && rows.length) {
        setSelectedTradeId(rows[0].id);
      }
    } catch (error) {
      message.error(getApiErrorMessage(error, "复盘交易记录加载失败。"));
    } finally {
      setLoadingTrades(false);
    }
  };

  const loadReports = async (tradeRecordId?: number | null) => {
    setLoadingReports(true);
    try {
      if (!token) {
        setReports([]);
        setSelectedReportId(null);
        return;
      }
      const data = await fetchReviewReports(tradeRecordId ?? undefined);
      setReports(data);
      setSelectedReportId(pickPreferredReportId(data));
    } catch (error) {
      message.error(getApiErrorMessage(error, "复盘报告加载失败。"));
    } finally {
      setLoadingReports(false);
    }
  };

  useEffect(() => {
    void loadTrades();
  }, [token]);

  useEffect(() => {
    if (selectedTradeId) {
      void loadReports(selectedTradeId);
    } else {
      setReports([]);
      setSelectedReportId(null);
    }
  }, [selectedTradeId, token]);

  const handleGenerate = async () => {
    if (!selectedTradeId) {
      message.warning("请先选择一笔交易。");
      return;
    }
    setGenerating(true);
    try {
      const data = await generateReviewReport(selectedTradeId);
      message.success("复盘报告已生成。");
      await loadReports(selectedTradeId);
      setSelectedReportId(data.id);
    } catch (error) {
      message.error(getApiErrorMessage(error, "复盘报告生成失败。"));
    } finally {
      setGenerating(false);
    }
  };

  const volumeEntries = selectedReport ? extractReviewMetricEntries(selectedReport.volume_analysis) : [];
  const chipEntries = selectedReport ? extractReviewMetricEntries(selectedReport.chip_analysis) : [];
  const trendEntries = selectedReport ? extractReviewMetricEntries(selectedReport.trend_analysis) : [];
  const priceChart: PriceChartPoint[] = (
    (selectedReport?.trend_analysis.price_chart as Omit<PriceChartPoint, "trade_label">[] | undefined) ?? []
  ).map((item) => ({
    ...item,
    trade_label: formatChartDate(item.trade_date),
  }));
  const volumeChart = ((selectedReport?.volume_analysis.volume_chart as VolumeChartPoint[] | undefined) ?? []).map((item) => ({
    ...item,
    trade_label: formatChartDate(item.trade_date),
  }));
  const canRenderCandles = hasCandlestickData(priceChart);
  const subscoreEntries = selectedReport
    ? [
        { label: "决策质量", value: selectedReport.subscores.decision_quality ?? 0 },
        { label: "环境匹配", value: selectedReport.subscores.context_alignment ?? 0 },
        { label: "执行质量", value: selectedReport.subscores.execution_quality ?? 0 },
        { label: "风险纪律", value: selectedReport.subscores.risk_discipline ?? 0 },
        { label: "情绪纪律", value: selectedReport.subscores.emotion_discipline ?? 0 },
      ]
    : [];
  const intentSummaryTags = summarizeIntentTags(selectedIntentSnapshot);
  const missingDataNotes = normalizeMissingDataNotes(selectedReport?.coach_report_payload?.missing_data_notes);
  const legacyEmptyReport = isLegacyEmptyReport(selectedReport);

  return (
    <div className="page-shell review-shell">
      <div className="page-header">
        <div>
          <Title className="page-title">复盘分析</Title>
          <Text className="page-description">选择交易、生成教练式复盘报告，并查看对应交易的历史版本。</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void loadTrades()} loading={loadingTrades}>
            刷新交易
          </Button>
          <Button type="primary" icon={<CalculatorOutlined />} onClick={() => void handleGenerate()} loading={generating}>
            生成复盘
          </Button>
        </Space>
      </div>

      <div className="review-layout">
        <Card className="surface-card section-card review-sidebar" variant="borderless">
          <div className="section-head">
            <div>
              <Title level={4} className="section-title">交易选择</Title>
              <Text type="secondary">先选择要复盘的交易，再查看对应报告历史。</Text>
            </div>
          </div>
          <Select
            showSearch
            style={{ width: "100%" }}
            placeholder="请选择一笔交易"
            optionFilterProp="label"
            value={selectedTradeId ?? undefined}
            onChange={(value) => setSelectedTradeId(value)}
            options={trades.map((trade) => ({
              value: trade.id,
              label: tradeLabel(trade),
            }))}
          />
          {selectedTrade ? (
            <div className="review-selected-trade">
              <Tag color={directionMeta(selectedTrade.direction).color}>{directionMeta(selectedTrade.direction).label}</Tag>
              <Tag color={marketMeta(selectedTrade.market).color}>{marketMeta(selectedTrade.market).label}</Tag>
              <Tag>{sourceLabel(selectedTrade.source)}</Tag>
              <Text type="secondary">价格 {selectedTrade.price}</Text>
              <Text type="secondary">数量 {selectedTrade.quantity}</Text>
              {intentSummaryTags.length ? <Text type="secondary">{intentSummaryTags.slice(0, 4).join(" · ")}</Text> : null}
            </div>
          ) : null}

          <div className="section-head review-history-head">
            <div>
              <Title level={4} className="section-title">
                <HistoryOutlined /> 报告历史
              </Title>
            </div>
          </div>
          <List
            loading={loadingReports}
            dataSource={reports}
            locale={{ emptyText: "该交易尚未生成复盘报告。" }}
            renderItem={(item) => (
              <List.Item
                className={`review-history-item ${selectedReportId === item.id ? "review-history-item-active" : ""}`}
                onClick={() => setSelectedReportId(item.id)}
              >
                <div className="dashboard-list-main">
                  <div className="dashboard-list-title">
                    <Text strong>V{item.version} · 评分 {item.overall_score}</Text>
                    <Text type="secondary">{formatDateTime(item.created_at)}</Text>
                  </div>
                  <Space wrap>
                    <Tag color={item.is_latest ? "green" : "default"}>{item.is_latest ? "最新" : "历史"}</Tag>
                    <Tag color="blue">{item.trade_summary.stock_code}</Tag>
                    <Tag color={directionMeta(item.trade_summary.direction).color}>
                      {directionMeta(item.trade_summary.direction).label}
                    </Tag>
                  </Space>
                </div>
              </List.Item>
            )}
          />
        </Card>

        {selectedReport ? (
          <div className="review-main">
            {legacyEmptyReport ? (
              <Alert
                type="warning"
                showIcon
                message="该复盘报告生成于旧版本，请重新点击“生成复盘”获取完整教练式报告。"
              />
            ) : null}
            <div className="stats-grid">
              <div className="stat-card review-score-card">
                <span className="stat-label">复盘评分</span>
                <span className="review-score-value">{selectedReport.overall_score}</span>
              </div>
              <div className="stat-card">
                <Statistic title="版本" value={`V${selectedReport.version}`} />
              </div>
              <div className="stat-card">
                <Statistic title="生成时间" value={formatDateTime(selectedReport.created_at)} />
              </div>
              <div className="stat-card">
                <Statistic title="交易时间" value={formatDateTime(selectedReport.trade_summary.trade_time)} />
              </div>
            </div>

            <div className="analysis-grid">
              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">交易前意图</Title>
                    <Text type="secondary">用户填写的主观交易意图与计划。</Text>
                  </div>
                </div>
                {renderIntentBlock(selectedIntentSnapshot)}
                <Paragraph style={{ marginTop: 12, marginBottom: 0 }}>
                  {selectedReport.coach_report_payload?.user_intent_summary}
                </Paragraph>
              </Card>

              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">客观判断</Title>
                    <Text type="secondary">由本地市场、行业、公司与技术证据给出的客观环境结论。</Text>
                  </div>
                </div>
                <Space direction="vertical" size={10} style={{ width: "100%", marginBottom: 12 }}>
                  <div>
                    <Text strong>市场热度：</Text>
                    <Text>{selectedReport.objective_summary?.market_heat}</Text>
                  </div>
                  <div>
                    <Text strong>行业热度：</Text>
                    <Text>{selectedReport.objective_summary?.industry_heat}</Text>
                  </div>
                  <div>
                    <Text strong>公司质地：</Text>
                    <Text>{selectedReport.objective_summary?.company_quality}</Text>
                  </div>
                </Space>
                <Paragraph style={{ marginBottom: 0 }}>
                  {selectedReport.coach_report_payload?.objective_context_summary}
                </Paragraph>
              </Card>

              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">偏差诊断</Title>
                    <Text type="secondary">主观标签与客观证据之间的偏差与误判来源。</Text>
                  </div>
                </div>
                <Tag color={selectedReport.intent_gap_diagnosis?.gap_level === "high" ? "red" : selectedReport.intent_gap_diagnosis?.gap_level === "medium" ? "orange" : "green"}>
                  偏差等级：{selectedReport.intent_gap_diagnosis?.gap_level ?? "unknown"}
                </Tag>
                <List
                  style={{ marginTop: 12 }}
                  dataSource={selectedReport.intent_gap_diagnosis?.gap_items ?? []}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />
              </Card>

              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">分项评分</Title>
                    <Text type="secondary">把总分拆到决策、环境、执行、风险与情绪五个维度。</Text>
                  </div>
                </div>
                <List
                  dataSource={subscoreEntries}
                  renderItem={(item) => (
                    <List.Item className="analysis-list-item">
                      <Text type="secondary">{item.label}</Text>
                      <Text strong>{item.value}</Text>
                    </List.Item>
                  )}
                />
              </Card>
            </div>

            <Card className="surface-card section-card" variant="borderless">
              <div className="section-head">
                <div>
                  <Title level={4} className="section-title">
                    <CheckCircleOutlined /> 教练结论与归因
                  </Title>
                  <Text type="secondary">把结构化证据转成决策质量、盈亏归因和模式结论。</Text>
                </div>
              </div>
              <Paragraph><Text strong>总体结论：</Text>{selectedReport.coach_report_payload?.overall_verdict}</Paragraph>
              <Paragraph><Text strong>Setup 复核：</Text>{selectedReport.coach_report_payload?.setup_review}</Paragraph>
              <Paragraph><Text strong>执行复核：</Text>{selectedReport.coach_report_payload?.execution_review}</Paragraph>
              <Paragraph><Text strong>风险计划复核：</Text>{selectedReport.coach_report_payload?.risk_plan_review}</Paragraph>
              {selectedReport.coach_report_payload?.exit_review ? (
                <Paragraph><Text strong>退出复核：</Text>{selectedReport.coach_report_payload.exit_review}</Paragraph>
              ) : null}
              <Paragraph><Text strong>盈亏归因：</Text>{selectedReport.coach_report_payload?.pnl_attribution}</Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                <Text strong>模式标签：</Text>
                <Tag color="blue" style={{ marginInlineStart: 8 }}>{selectedReport.coach_report_payload?.pattern_tag}</Tag>
              </Paragraph>
            </Card>

            <Card className="surface-card section-card" variant="borderless">
              <div className="section-head">
                <div>
                  <Title level={4} className="section-title">后续建议</Title>
                  <Text type="secondary">区分“当前这笔交易怎么处理”和“下次再遇到同类单子怎么做”。</Text>
                </div>
              </div>
              <Paragraph><Text strong>当前建议：</Text>{selectedReport.coach_report_payload?.follow_up_advice}</Paragraph>
              <List
                header={<Text strong>下次执行规则</Text>}
                dataSource={selectedReport.coach_report_payload?.next_time_rules ?? []}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
              {missingDataNotes.length ? (
                <Alert type="warning" showIcon message={missingDataNotes.join("；")} />
              ) : null}
            </Card>

            <div className="review-chart-grid">
              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">价格主图</Title>
                    <Text type="secondary">
                      {canRenderCandles ? "标准 K 线叠加 MA5 / MA10 / MA20，并标出支撑与压力位。" : "旧报告缺少完整 OHLC 数据，当前回退为收盘价折线图。"}
                    </Text>
                  </div>
                </div>
                {priceChart.length ? (
                  <div className="chart-shell review-chart-shell">
                    {!canRenderCandles ? (
                      <Space direction="vertical" size={12} style={{ width: "100%" }}>
                        <Alert
                          type="info"
                          showIcon
                          message="当前报告生成于 K 线图上线之前。重新点击“生成复盘”后，会用完整 OHLC 数据重建为标准 K 线。"
                        />
                        <ResponsiveContainer width="100%" height={320}>
                          <ComposedChart data={priceChart}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(17,100,102,0.12)" />
                            <XAxis dataKey="trade_label" />
                            <YAxis domain={["auto", "auto"]} />
                            <Tooltip />
                            <Legend />
                            <ReferenceLine y={priceChart[priceChart.length - 1]?.support} stroke="#2d6a4f" strokeDasharray="4 4" label="支撑" />
                            <ReferenceLine y={priceChart[priceChart.length - 1]?.resistance} stroke="#b42318" strokeDasharray="4 4" label="压力" />
                            <Line type="monotone" dataKey="close" name="收盘价" stroke="#116466" dot={false} strokeWidth={2.5} />
                            <Line type="monotone" dataKey="ma5" name="MA5" stroke="#d8a14d" dot={false} />
                            <Line type="monotone" dataKey="ma10" name="MA10" stroke="#a45f2a" dot={false} />
                            <Line type="monotone" dataKey="ma20" name="MA20" stroke="#51606d" dot={false} />
                          </ComposedChart>
                        </ResponsiveContainer>
                      </Space>
                    ) : (
                      <ReviewPriceCandlestickChart data={priceChart} />
                    )}
                  </div>
                ) : (
                  <div className="empty-note">当前报告没有可展示的价格图数据。</div>
                )}
              </Card>

              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">量能图</Title>
                    <Text type="secondary">显示成交量柱和 5 / 10 / 20 日均量线。</Text>
                  </div>
                </div>
                {volumeChart.length ? (
                  <div className="chart-shell review-chart-shell">
                    <ResponsiveContainer width="100%" height={320}>
                      <ComposedChart data={volumeChart}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(17,100,102,0.12)" />
                        <XAxis dataKey="trade_label" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="volume" name="成交量" fill="rgba(17,100,102,0.4)" />
                        <Line type="monotone" dataKey="avg_volume_5" name="5日均量" stroke="#d8a14d" dot={false} />
                        <Line type="monotone" dataKey="avg_volume_10" name="10日均量" stroke="#a45f2a" dot={false} />
                        <Line type="monotone" dataKey="avg_volume_20" name="20日均量" stroke="#51606d" dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="empty-note">当前报告没有可展示的量能图数据。</div>
                )}
              </Card>
            </div>

            <div className="analysis-grid">
              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">
                      <RiseOutlined /> 量能证据
                    </Title>
                  </div>
                </div>
                <AnalysisDataStatus payload={selectedReport.volume_analysis} />
                <List
                  dataSource={volumeEntries}
                  renderItem={(item) => (
                    <List.Item className="analysis-list-item">
                      <Text type="secondary">{item.label}</Text>
                      <Text strong>{item.display}</Text>
                    </List.Item>
                  )}
                />
              </Card>

              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">
                      <RadarChartOutlined /> 筹码证据
                    </Title>
                  </div>
                </div>
                <AnalysisDataStatus payload={selectedReport.chip_analysis} />
                <List
                  dataSource={chipEntries}
                  renderItem={(item) => (
                    <List.Item className="analysis-list-item">
                      <Text type="secondary">{item.label}</Text>
                      <Text strong>{item.display}</Text>
                    </List.Item>
                  )}
                />
              </Card>

              <Card className="surface-card section-card" variant="borderless">
                <div className="section-head">
                  <div>
                    <Title level={4} className="section-title">
                      <ThunderboltOutlined /> 趋势证据
                    </Title>
                  </div>
                </div>
                <AnalysisDataStatus payload={selectedReport.trend_analysis} />
                <List
                  dataSource={trendEntries}
                  renderItem={(item) => (
                    <List.Item className="analysis-list-item">
                      <Text type="secondary">{item.label}</Text>
                      <Text strong>{item.display}</Text>
                    </List.Item>
                  )}
                />
              </Card>
            </div>
          </div>
        ) : (
          <Card className="surface-card section-card" variant="borderless">
            <Empty description="先选择一笔交易并生成复盘报告，再查看分析详情。" />
          </Card>
        )}
      </div>
    </div>
  );
}
