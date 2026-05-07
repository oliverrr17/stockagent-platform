import { BellOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Card, Drawer, Input, Select, Space, Tag, Typography, message } from "antd";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { fetchNews } from "../api/news";
import { runOperation } from "../api/status";
import { useApiSettings } from "../context/ApiSettingsContext";
import type { NewsItem, NewsCategory } from "../types";
import {
  formatDateTime,
  newsCategoryMeta,
  notificationChannelMeta,
  notificationStatusMeta,
  priorityMeta,
  pushedMeta,
  sourceLabel,
} from "../utils/display";
import { getApiErrorMessage } from "../utils/errors";
import { formatNewsActionResult, type FormattedOperationResult } from "../utils/operations";

const { Title, Text, Paragraph, Link } = Typography;

const CATEGORY_VALUES: NewsCategory[] = ["ANNOUNCEMENT", "SENTIMENT", "RESEARCH", "INDUSTRY"];

export function NewsPage() {
  const {
    settings: { token },
  } = useApiSettings();
  const [stockCodeInput, setStockCodeInput] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [category, setCategory] = useState<string | undefined>();
  const [source, setSource] = useState<string | undefined>();
  const [priorityLevel, setPriorityLevel] = useState<string | undefined>();
  const [pushed, setPushed] = useState<string | undefined>();
  const [selected, setSelected] = useState<NewsItem | null>(null);
  const [runningAction, setRunningAction] = useState("");
  const [lastActionResult, setLastActionResult] = useState<FormattedOperationResult | null>(null);
  const deferredStockCode = useDeferredValue(stockCodeInput.trim().toUpperCase());
  const deferredQuery = useDeferredValue(queryInput.trim());
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadNews = async () => {
    setLoading(true);
    try {
      if (!token) {
        setItems([]);
        return;
      }
      const data = await fetchNews({
        stock_code: deferredStockCode || undefined,
        category: category || undefined,
        source: source || undefined,
        pushed: pushed === undefined ? undefined : pushed === "true",
        query: deferredQuery || undefined,
        ordering: "-published_at",
      });
      setItems(data);
    } catch (error) {
      message.error(getApiErrorMessage(error, "新闻数据加载失败。"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadNews();
  }, [token, deferredStockCode, deferredQuery, category, source, pushed]);

  const filteredItems = useMemo(
    () => items.filter((item) => (priorityLevel ? item.priority_level === priorityLevel : true)),
    [items, priorityLevel],
  );

  const stats = useMemo(() => {
    const announcementCount = filteredItems.filter((item) => item.category === "ANNOUNCEMENT").length;
    const researchCount = filteredItems.filter((item) => item.category === "RESEARCH").length;
    const pushedCount = filteredItems.filter((item) => item.pushed).length;
    const p1Count = filteredItems.filter((item) => item.priority_level === "P1").length;
    return [
      { label: "当前新闻数", value: filteredItems.length.toString() },
      { label: "公告数", value: announcementCount.toString() },
      { label: "研报数", value: researchCount.toString() },
      { label: "已推送数", value: pushedCount.toString() },
      { label: "即时级数量", value: p1Count.toString() },
    ];
  }, [filteredItems]);

  const sourceOptions = Array.from(new Set(items.map((item) => item.source))).map((value) => ({
    label: sourceLabel(value),
    value,
  }));

  const triggerAction = async (action: "crawl-news" | "push-news" | "push-digest") => {
    setRunningAction(action);
    try {
      const result = await runOperation(action);
      setLastActionResult(formatNewsActionResult(result));
      message.success("操作执行完成。");
      await loadNews();
    } catch (error) {
      message.error(getApiErrorMessage(error, "新闻操作执行失败。"));
    } finally {
      setRunningAction("");
    }
  };

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <Title className="page-title">新闻动态</Title>
          <Text className="page-description">按股票、来源、优先级和推送状态筛选新闻，并查看单条详情。</Text>
        </div>
        <Space wrap>
          <Button loading={runningAction === "crawl-news"} onClick={() => void triggerAction("crawl-news")}>
            抓取最新新闻
          </Button>
          <Button loading={runningAction === "push-news"} onClick={() => void triggerAction("push-news")}>
            推送即时通知
          </Button>
          <Button loading={runningAction === "push-digest"} onClick={() => void triggerAction("push-digest")}>
            发送摘要邮件
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => void loadNews()} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      {lastActionResult ? (
        <Card className="surface-card section-card" variant="borderless">
          <div className="section-head">
            <div>
              <Title level={4} className="section-title">
                最近一次操作结果
              </Title>
            </div>
          </div>
          <div className="detail-stack">
            {lastActionResult.lines.map((line) => (
              <Text key={line}>{line}</Text>
            ))}
          </div>
        </Card>
      ) : null}

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
            <Title level={4} className="section-title">
              筛选条件
            </Title>
            <Text type="secondary">缩小结果范围，再决定哪些值得关注和推送。</Text>
          </div>
        </div>
        <div className="filter-row">
          <Input
            placeholder="按股票代码筛选"
            prefix={<SearchOutlined />}
            value={stockCodeInput}
            onChange={(event) => setStockCodeInput(event.target.value)}
          />
          <Input
            placeholder="按标题或摘要搜索"
            prefix={<SearchOutlined />}
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
          />
          <Select
            allowClear
            placeholder="分类"
            value={category}
            onChange={setCategory}
            options={CATEGORY_VALUES.map((value) => ({
              value,
              label: newsCategoryMeta(value).label,
            }))}
          />
          <Select allowClear placeholder="来源" value={source} onChange={setSource} options={sourceOptions} />
          <Select
            allowClear
            placeholder="优先级"
            value={priorityLevel}
            onChange={setPriorityLevel}
            options={[
              { value: "P1", label: "即时" },
              { value: "P2", label: "摘要" },
              { value: "P3", label: "仅入库" },
            ]}
          />
          <Select
            allowClear
            placeholder="推送状态"
            value={pushed}
            onChange={setPushed}
            options={[
              { value: "true", label: "已推送" },
              { value: "false", label: "未推送" },
            ]}
          />
        </div>
      </Card>

      <div className="news-feed">
        {filteredItems.map((item) => (
          <Card
            key={item.id}
            className="surface-card section-card news-card news-card-clickable"
            variant="borderless"
            onClick={() => setSelected(item)}
          >
            <Space direction="vertical" size={10} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color={newsCategoryMeta(item.category).color}>{newsCategoryMeta(item.category).label}</Tag>
                <Tag color={priorityMeta(item.priority_level).color}>{priorityMeta(item.priority_level).label}</Tag>
                <Tag>{sourceLabel(item.source)}</Tag>
                <Tag icon={<BellOutlined />} color={pushedMeta(item.pushed).color}>
                  {pushedMeta(item.pushed).label}
                </Tag>
                {item.latest_notification_status ? (
                  <Tag color={notificationStatusMeta(item.latest_notification_status).color}>
                    最新通知 {notificationStatusMeta(item.latest_notification_status).label}
                  </Tag>
                ) : null}
                {item.latest_notification_channel ? (
                  <Tag color={notificationChannelMeta(item.latest_notification_channel).color}>
                    {notificationChannelMeta(item.latest_notification_channel).label}
                  </Tag>
                ) : null}
                <Tag>{item.stock_code}</Tag>
              </Space>
              <Title level={4} className="section-title">
                {item.title}
              </Title>
              <Paragraph className="news-summary">{item.summary || "该来源未提供摘要。"}</Paragraph>
              <div className="news-meta-line">
                <Text type="secondary">优先级分数 {item.priority_score}</Text>
                <Text type="secondary">{formatDateTime(item.published_at)}</Text>
              </div>
            </Space>
          </Card>
        ))}
        {!loading && filteredItems.length === 0 ? (
          <Card className="surface-card section-card" variant="borderless">
            <div className="empty-note">没有符合当前筛选条件的新闻。</div>
          </Card>
        ) : null}
      </div>

      <Drawer
        title={selected ? `新闻详情 · ${selected.stock_code}` : "新闻详情"}
        width={720}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
      >
        {selected ? (
          <div className="detail-stack">
            <Space wrap>
              <Tag color={newsCategoryMeta(selected.category).color}>{newsCategoryMeta(selected.category).label}</Tag>
              <Tag color={priorityMeta(selected.priority_level).color}>{priorityMeta(selected.priority_level).label}</Tag>
              <Tag color={pushedMeta(selected.pushed).color}>{pushedMeta(selected.pushed).label}</Tag>
              <Tag>{sourceLabel(selected.source)}</Tag>
              {selected.latest_notification_status ? (
                <Tag color={notificationStatusMeta(selected.latest_notification_status).color}>
                  {notificationStatusMeta(selected.latest_notification_status).label}
                </Tag>
              ) : null}
            </Space>
            <Title level={4} className="section-title">
              {selected.title}
            </Title>
            <Text type="secondary">
              {selected.stock_code} · {formatDateTime(selected.published_at)} · 通知记录 {selected.notification_count}
            </Text>
            <Paragraph>{selected.summary || "该来源未提供摘要。"}</Paragraph>
            <div className="rules-block">
              <Text type="secondary">命中规则</Text>
              <Space wrap>
                {selected.matched_rules.map((rule) => (
                  <Tag key={`${selected.id}-${rule}`}>{rule}</Tag>
                ))}
              </Space>
            </div>
            <Text>优先级分数：{selected.priority_score}</Text>
            <Link href={selected.url} target="_blank" rel="noreferrer">
              打开原文
            </Link>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
