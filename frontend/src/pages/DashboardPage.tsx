import { AlertOutlined, ArrowRightOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, List, Space, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchNews } from "../api/news";
import { fetchActivePositions } from "../api/portfolio";
import { fetchOperationsStatus } from "../api/status";
import { fetchTrades } from "../api/trades";
import { useApiSettings } from "../context/ApiSettingsContext";
import type { NewsItem, OperationsStatus, Position, TradeRecord } from "../types";
import {
  directionMeta,
  formatDateTime,
  marketMeta,
  newsCategoryMeta,
  positionStatusMeta,
  priorityMeta,
  pushedMeta,
  sourceLabel,
} from "../utils/display";
import { getApiErrorMessage } from "../utils/errors";

const { Title, Text, Link } = Typography;

function formatMoney(value: number) {
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function DashboardPage() {
  const {
    settings: { token },
  } = useApiSettings();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [ops, setOps] = useState<OperationsStatus | null>(null);

  const loadDashboard = async () => {
    setLoading(true);
    try {
      if (!token) {
        setPositions([]);
        setTrades([]);
        setNews([]);
        setOps(null);
        return;
      }

      const [activePositions, tradeRows, newsRows, status] = await Promise.all([
        fetchActivePositions(),
        fetchTrades({ ordering: "-trade_time" }),
        fetchNews({ ordering: "-published_at" }),
        fetchOperationsStatus(),
      ]);

      setPositions(activePositions);
      setTrades(tradeRows.slice(0, 6));
      setNews(newsRows);
      setOps(status);
    } catch (error) {
      message.error(getApiErrorMessage(error, "总览数据加载失败。"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, [token]);

  const aSharePositions = positions.filter((item) => item.market === "A_STOCK");
  const hkPositions = positions.filter((item) => item.market === "HK_STOCK");
  const pendingNews = news.filter((item) => !item.pushed).length;
  const p1Count = news.filter((item) => item.priority_level === "P1").length;
  const latestAnnouncements = [...news]
    .filter((item) => item.category === "ANNOUNCEMENT" || item.priority_level === "P1")
    .slice(0, 4);
  const stats = [
    { label: "活跃持仓", value: positions.length.toString() },
    { label: "A股持仓", value: aSharePositions.length.toString() },
    { label: "港股持仓", value: hkPositions.length.toString() },
    { label: "待处理新闻", value: pendingNews.toString() },
    { label: "即时级新闻", value: p1Count.toString() },
    { label: "最新日志", value: ops?.recent_logs[0] ? formatDateTime(ops.recent_logs[0].updated_at * 1000) : "--" },
  ];

  return (
    <div className="page-shell dashboard-shell">
      <div className="page-header">
        <div>
          <Title className="page-title">总览</Title>
          <Text className="page-description">开盘即看：持仓、成交、公告、异常提醒和任务状态集中展示。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void loadDashboard()} loading={loading}>
          刷新
        </Button>
      </div>

      {ops?.alerts.length ? (
        <div className="alert-grid">
          {ops.alerts.map((alert) => (
            <Alert
              key={`${alert.title}-${alert.message}`}
              type={alert.severity === "error" ? "error" : "warning"}
              message={alert.title}
              description={alert.message}
              showIcon
            />
          ))}
        </div>
      ) : null}

      <div className="dashboard-kpi-grid">
        {stats.map((item) => (
          <div key={item.label} className="dashboard-kpi">
            <span className="dashboard-kpi-label">{item.label}</span>
            <span className="dashboard-kpi-value">{item.value}</span>
          </div>
        ))}
      </div>

      <Card className="surface-card section-card" variant="borderless">
        <div className="section-head">
          <div>
            <Title level={4} className="section-title">
              快捷入口
            </Title>
            <Text type="secondary">从总览页直接下钻到最常用的操作面板。</Text>
          </div>
        </div>
        <div className="quick-link-grid">
          {[
            { title: "持仓管理", desc: "查看来源并管理手动持仓", path: "/portfolio" },
            { title: "新闻动态", desc: "筛选即时、摘要与未推送新闻", path: "/news" },
            { title: "通知中心", desc: "查看推送日志和命中规则", path: "/notifications" },
            { title: "运行状态", desc: "查看调度时间和日志", path: "/operations" },
            { title: "操作中心", desc: "手动执行抓取和推送任务", path: "/control" },
            { title: "复盘分析", desc: "查看交易报告历史", path: "/review" },
          ].map((item) => (
            <button key={item.path} className="quick-link-card" type="button" onClick={() => navigate(item.path)}>
              <span className="quick-link-title">{item.title}</span>
              <span className="quick-link-desc">{item.desc}</span>
              <span className="quick-link-arrow">
                <ArrowRightOutlined />
              </span>
            </button>
          ))}
        </div>
      </Card>

      <div className="dashboard-grid">
        <Card className="surface-card section-card" variant="borderless">
          <div className="section-head">
            <div>
              <Title level={4} className="section-title">
                最新交易
              </Title>
              <Text type="secondary">按时间倒序显示最近入库成交。</Text>
            </div>
          </div>
          <List
            dataSource={trades}
            locale={{ emptyText: "暂无近期交易。" }}
            renderItem={(item) => (
              <List.Item className="dashboard-list-item">
                <div className="dashboard-list-main">
                  <div className="dashboard-list-title">
                    <Text strong>
                      {item.stock_code} {item.stock_name}
                    </Text>
                    <Text type="secondary">{formatDateTime(item.trade_time)}</Text>
                  </div>
                  <Space wrap>
                    <Tag color={directionMeta(item.direction).color}>{directionMeta(item.direction).label}</Tag>
                    <Tag color={marketMeta(item.market).color}>{marketMeta(item.market).label}</Tag>
                    <Tag>{sourceLabel(item.source)}</Tag>
                  </Space>
                </div>
                <div className="dashboard-list-meta">
                  <Text strong>{formatMoney(Number(item.price) * item.quantity)}</Text>
                  <Text type="secondary">{item.quantity} 股</Text>
                </div>
              </List.Item>
            )}
          />
        </Card>

        <Card className="surface-card section-card" variant="borderless">
          <div className="section-head">
            <div>
              <Title level={4} className="section-title">
                持仓快照
              </Title>
              <Text type="secondary">当前活跃持仓的数量、成本和状态。</Text>
            </div>
          </div>
          <List
            dataSource={positions.slice(0, 6)}
            locale={{ emptyText: "暂无活跃持仓。" }}
            renderItem={(item) => (
              <List.Item className="dashboard-list-item">
                <div className="dashboard-list-main">
                  <div className="dashboard-list-title">
                    <Text strong>
                      {item.stock_code} {item.stock_name}
                    </Text>
                    <Text type="secondary">数量 {item.quantity} 股</Text>
                  </div>
                  <Space wrap>
                    <Tag color={marketMeta(item.market).color}>{marketMeta(item.market).label}</Tag>
                    <Tag color={positionStatusMeta(item.status).color}>{positionStatusMeta(item.status).label}</Tag>
                  </Space>
                </div>
                <div className="dashboard-list-meta">
                  <Text type="secondary">成本 {formatMoney(Number(item.weighted_avg_cost))}</Text>
                  <Text strong>{formatMoney(Number(item.total_invested))}</Text>
                </div>
              </List.Item>
            )}
          />
        </Card>

        <Card className="surface-card section-card" variant="borderless">
          <div className="section-head">
            <div>
              <Title level={4} className="section-title">
                任务状态
              </Title>
              <Text type="secondary">今日关键任务时间与当前待处理数量。</Text>
            </div>
          </div>
          {ops ? (
            <div className="ops-status-list">
              {[
                ["THS", ops.scheduler.ths],
                ["HSBC", ops.scheduler.hsbc],
                ["新闻抓取", ops.scheduler.news_fetch],
                ["摘要推送", ops.scheduler.news_digest],
                ["待处理新闻", String(ops.counts.news_pending)],
                ["最近日志", ops.recent_logs[0]?.name ?? "--"],
              ].map(([label, value]) => (
                <div key={String(label)} className="ops-status-row">
                  <Text type="secondary">{label}</Text>
                  <Text strong>{value}</Text>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-note">暂无运行状态快照。</div>
          )}
        </Card>

        <Card className="surface-card section-card dashboard-span-2" variant="borderless">
          <div className="section-head">
            <div>
              <Title level={4} className="section-title">
                公告雷达
              </Title>
              <Text type="secondary">只保留高信号公告与即时级新闻。</Text>
            </div>
            <Button type="link" onClick={() => navigate("/news")}>
              查看全部
            </Button>
          </div>
          <div className="news-feed">
            {latestAnnouncements.map((item) => (
              <Card key={item.id} className="surface-card news-card dashboard-news-card" variant="borderless">
                <Space direction="vertical" size={10} style={{ width: "100%" }}>
                  <Space wrap>
                    <Tag color={newsCategoryMeta(item.category).color}>{newsCategoryMeta(item.category).label}</Tag>
                    <Tag color={priorityMeta(item.priority_level).color}>{priorityMeta(item.priority_level).label}</Tag>
                    <Tag>{sourceLabel(item.source)}</Tag>
                    <Tag icon={<AlertOutlined />} color={pushedMeta(item.pushed).color}>
                      {pushedMeta(item.pushed).label}
                    </Tag>
                    <Tag>{item.stock_code}</Tag>
                  </Space>
                  <Title level={5} className="section-title">
                    {item.title}
                  </Title>
                  <Text type="secondary">{formatDateTime(item.published_at)}</Text>
                  <Text className="compact-summary">{item.summary || "该来源未提供摘要。"}</Text>
                  <Link href={item.url} target="_blank" rel="noreferrer">
                    打开原文
                  </Link>
                </Space>
              </Card>
            ))}
            {latestAnnouncements.length === 0 ? (
              <Card className="surface-card section-card" variant="borderless">
                <div className="empty-note">暂无公告类新闻。</div>
              </Card>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  );
}
