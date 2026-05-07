import { BellOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Card, Drawer, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { fetchNotificationLogs } from "../api/news";
import { useApiSettings } from "../context/ApiSettingsContext";
import type { NotificationLog } from "../types";
import {
  formatDateTime,
  newsCategoryMeta,
  notificationChannelMeta,
  notificationStatusMeta,
  priorityMeta,
  sourceLabel,
} from "../utils/display";
import { getApiErrorMessage } from "../utils/errors";

const { Title, Text } = Typography;

export function NotificationCenterPage() {
  const {
    settings: { token },
  } = useApiSettings();
  const [stockCodeInput, setStockCodeInput] = useState("");
  const [status, setStatus] = useState<string>();
  const [channel, setChannel] = useState<string>();
  const [rows, setRows] = useState<NotificationLog[]>([]);
  const [selected, setSelected] = useState<NotificationLog | null>(null);
  const [loading, setLoading] = useState(false);
  const deferredStockCode = useDeferredValue(stockCodeInput.trim().toUpperCase());

  const loadLogs = async () => {
    setLoading(true);
    try {
      if (!token) {
        setRows([]);
        return;
      }
      const data = await fetchNotificationLogs({
        stock_code: deferredStockCode || undefined,
        status,
        channel,
        ordering: "-id",
      });
      setRows(data);
    } catch (error) {
      message.error(getApiErrorMessage(error, "通知日志加载失败。"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadLogs();
  }, [token, deferredStockCode, status, channel]);

  const stats = useMemo(
    () => [
      { label: "日志总数", value: rows.length.toString() },
      { label: "成功", value: rows.filter((item) => item.status === "SUCCESS").length.toString() },
      { label: "失败", value: rows.filter((item) => item.status === "FAILED").length.toString() },
      { label: "待发送", value: rows.filter((item) => item.status === "PENDING").length.toString() },
    ],
    [rows],
  );

  const columns: ColumnsType<NotificationLog> = [
    {
      title: "新闻",
      dataIndex: "news_title",
      key: "news_title",
      render: (value, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text type="secondary">
            {record.stock_code} · {sourceLabel(record.news_source)}
          </Text>
        </Space>
      ),
    },
    {
      title: "优先级",
      key: "priority_level",
      render: (_, record) => <Tag color={priorityMeta(record.priority_level).color}>{priorityMeta(record.priority_level).label}</Tag>,
    },
    {
      title: "通道",
      key: "channel",
      render: (_, record) => <Tag color={notificationChannelMeta(record.channel).color}>{notificationChannelMeta(record.channel).label}</Tag>,
    },
    {
      title: "状态",
      key: "status",
      render: (_, record) => <Tag color={notificationStatusMeta(record.status).color}>{notificationStatusMeta(record.status).label}</Tag>,
    },
    {
      title: "发送时间",
      dataIndex: "sent_at",
      key: "sent_at",
      render: (value) => (value ? formatDateTime(value) : "未发送"),
    },
  ];

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <Title className="page-title">通知中心</Title>
          <Text className="page-description">查看每条新闻的推送结果、命中规则和当前通知状态。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void loadLogs()} loading={loading}>
          刷新
        </Button>
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
            <Title level={4} className="section-title">
              筛选条件
            </Title>
            <Text type="secondary">按股票、状态和发送通道筛选通知日志。</Text>
          </div>
        </div>
        <div className="filter-row">
          <Input value={stockCodeInput} onChange={(event) => setStockCodeInput(event.target.value)} placeholder="股票代码" />
          <Select
            allowClear
            value={status}
            onChange={setStatus}
            placeholder="状态"
            options={[
              { label: "成功", value: "SUCCESS" },
              { label: "失败", value: "FAILED" },
              { label: "待发送", value: "PENDING" },
            ]}
          />
          <Select
            allowClear
            value={channel}
            onChange={setChannel}
            placeholder="通道"
            options={[
              { label: "邮件", value: "EMAIL" },
              { label: "微信", value: "WECHAT" },
              { label: "Telegram", value: "TELEGRAM" },
            ]}
          />
        </div>
      </Card>

      <Card className="surface-card section-card table-card" variant="borderless">
        <Table
          size="small"
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          onRow={(record) => ({
            onClick: () => setSelected(record),
          })}
          locale={{ emptyText: <div className="empty-note">暂无通知日志。</div> }}
        />
      </Card>

      <Drawer
        title={selected ? `通知详情 · ${selected.stock_code}` : "通知详情"}
        width={640}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
      >
        {selected ? (
          <div className="detail-stack">
            <Space wrap>
              <Tag color={newsCategoryMeta(selected.news_category).color}>{newsCategoryMeta(selected.news_category).label}</Tag>
              <Tag color={priorityMeta(selected.priority_level).color}>{priorityMeta(selected.priority_level).label}</Tag>
              <Tag color={notificationStatusMeta(selected.status).color}>{notificationStatusMeta(selected.status).label}</Tag>
              <Tag color={notificationChannelMeta(selected.channel).color}>{notificationChannelMeta(selected.channel).label}</Tag>
            </Space>
            <Title level={4} className="section-title">
              {selected.news_title}
            </Title>
            <Text type="secondary">
              {selected.stock_code} · {sourceLabel(selected.news_source)} · {formatDateTime(selected.news_published_at)}
            </Text>
            <div className="rules-block">
              <Text type="secondary">命中规则</Text>
              <Space wrap>
                {selected.matched_rules.map((rule) => (
                  <Tag key={`${selected.id}-${rule}`}>{rule}</Tag>
                ))}
              </Space>
            </div>
            <Text>优先级分数：{selected.priority_score}</Text>
            <Text>重试次数：{selected.retry_count}</Text>
            <Text>{selected.sent_at ? `发送时间：${formatDateTime(selected.sent_at)}` : "尚未发送"}</Text>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
