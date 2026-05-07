import { ClockCircleOutlined, FileTextOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, List, Space, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchOperationsStatus } from "../api/status";
import { useApiSettings } from "../context/ApiSettingsContext";
import type { OperationsStatus } from "../types";
import { formatDateTime } from "../utils/display";
import { getApiErrorMessage } from "../utils/errors";

const { Title, Text } = Typography;

export function OperationsPage() {
  const {
    settings: { token },
  } = useApiSettings();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<OperationsStatus | null>(null);

  const loadStatus = async () => {
    setLoading(true);
    try {
      if (!token) {
        setStatus(null);
        return;
      }
      const data = await fetchOperationsStatus();
      setStatus(data);
    } catch (error) {
      message.error(getApiErrorMessage(error, "运行状态加载失败。"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, [token]);

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <Title className="page-title">运行状态</Title>
          <Text className="page-description">查看调度时间、异常提醒和最近一次任务执行日志。</Text>
        </div>
        <Space>
          <Button onClick={() => navigate("/control")}>前往操作中心</Button>
          <Button icon={<ReloadOutlined />} onClick={() => void loadStatus()} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      {status?.alerts.length ? (
        <div className="alert-grid">
          {status.alerts.map((alert) => (
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

      {status ? (
        <>
          <div className="dashboard-kpi-grid">
            {[
              ["待处理新闻", status.counts.news_pending],
              ["已推送新闻", status.counts.news_pushed],
              ["通知日志数", status.counts.notification_logs],
              ["活跃持仓", status.counts.active_positions],
            ].map(([label, value]) => (
              <div key={String(label)} className="dashboard-kpi">
                <span className="dashboard-kpi-label">{label}</span>
                <span className="dashboard-kpi-value">{value}</span>
              </div>
            ))}
          </div>

          <Card className="surface-card section-card" variant="borderless">
            <div className="section-head">
              <div>
                <Title level={4} className="section-title">
                  调度时间
                </Title>
                <Text type="secondary">每日抓取与摘要任务的计划时间。</Text>
              </div>
            </div>
            <div className="ops-summary-grid">
              <div className="ops-pill">
                <ClockCircleOutlined />
                <span>THS</span>
                <strong>{status.scheduler.ths}</strong>
              </div>
              <div className="ops-pill">
                <ClockCircleOutlined />
                <span>HSBC</span>
                <strong>{status.scheduler.hsbc}</strong>
              </div>
              <div className="ops-pill">
                <ClockCircleOutlined />
                <span>新闻抓取</span>
                <strong>{status.scheduler.news_fetch}</strong>
              </div>
              <div className="ops-pill">
                <ClockCircleOutlined />
                <span>P2 摘要</span>
                <strong>{status.scheduler.news_digest}</strong>
              </div>
              <div className="ops-pill">
                <ClockCircleOutlined />
                <span>交易总数</span>
                <strong>{status.counts.trades_total}</strong>
              </div>
              <div className="ops-pill">
                <ClockCircleOutlined />
                <span>新闻总数</span>
                <strong>{status.counts.news_total}</strong>
              </div>
            </div>
          </Card>

          <Card className="surface-card section-card" variant="borderless">
            <div className="section-head">
              <div>
                <Title level={4} className="section-title">
                  最近任务日志
                </Title>
                <Text type="secondary">直接来自后端主机的最近几份调度日志。</Text>
              </div>
            </div>
            <List
              dataSource={status.recent_logs}
              locale={{ emptyText: "暂无调度日志。" }}
              renderItem={(item) => (
                <List.Item className="dashboard-list-item">
                  <div className="dashboard-list-main">
                    <div className="dashboard-list-title">
                      <Space>
                        <FileTextOutlined />
                        <Text strong>{item.name}</Text>
                      </Space>
                      <div className="log-preview">
                        {item.preview.slice(-2).map((line, index) => (
                          <Text key={`${item.name}-${index}`} type="secondary" className="log-preview-line">
                            {line}
                          </Text>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="dashboard-list-meta">
                    <Text type="secondary">{formatDateTime(item.updated_at * 1000)}</Text>
                    <Text strong>{item.last_line || "没有最终日志行"}</Text>
                  </div>
                </List.Item>
              )}
            />
          </Card>
        </>
      ) : null}
    </div>
  );
}
