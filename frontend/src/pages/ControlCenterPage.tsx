import { PlayCircleOutlined, ReloadOutlined, SyncOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Space, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { runOperation, fetchOperationsStatus } from "../api/status";
import { useApiSettings } from "../context/ApiSettingsContext";
import type { OperationsActionResult, OperationsStatus } from "../types";
import { getApiErrorMessage } from "../utils/errors";

const { Title, Text, Paragraph } = Typography;

const ACTIONS = [
  { key: "run-daily", title: "执行每日总采集", description: "顺序执行 THS 成交抓取与 HSBC 邮件抓取。" },
  { key: "run-ths", title: "抓取 THS 成交", description: "只执行 A 股当日成交抓取。" },
  { key: "run-hsbc", title: "抓取汇丰邮件", description: "只执行港股邮件解析与入库。" },
  { key: "sync-ths-positions", title: "同步 THS 当前持仓", description: "将当前同花顺持仓快照同步进后台。" },
  { key: "crawl-news", title: "抓取持仓新闻", description: "针对当前活跃持仓抓取 A 股和港股新闻。" },
  { key: "push-news", title: "推送即时通知", description: "处理当前待推送的即时级新闻。" },
  { key: "push-digest", title: "发送摘要邮件", description: "汇总当前 P2 新闻并发送摘要邮件。" },
];

export function ControlCenterPage() {
  const {
    settings: { token },
  } = useApiSettings();
  const [running, setRunning] = useState<string>("");
  const [status, setStatus] = useState<OperationsStatus | null>(null);
  const [lastResult, setLastResult] = useState<OperationsActionResult | null>(null);

  const loadStatus = async () => {
    if (!token) {
      setStatus(null);
      return;
    }

    try {
      setStatus(await fetchOperationsStatus());
    } catch (error) {
      message.error(getApiErrorMessage(error, "运行状态刷新失败。"));
    }
  };

  useEffect(() => {
    void loadStatus();
  }, [token]);

  const trigger = async (action: string) => {
    setRunning(action);
    try {
      const result = await runOperation(action);
      setLastResult(result);
      message.success("操作执行完成。");
      await loadStatus();
    } catch (error) {
      message.error(getApiErrorMessage(error, "操作执行失败。"));
    } finally {
      setRunning("");
    }
  };

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <Title className="page-title">操作中心</Title>
          <Text className="page-description">将常用运维动作从命令行搬到前端，便于手动补跑与排障。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void loadStatus()}>
          刷新状态
        </Button>
      </div>

      {status?.alerts.length ? (
        <div className="alert-grid">
          {status.alerts.map((alert) => (
            <Alert key={`${alert.title}-${alert.message}`} type={alert.severity === "error" ? "error" : "warning"} message={alert.title} description={alert.message} showIcon />
          ))}
        </div>
      ) : null}

      <div className="ops-action-grid">
        {ACTIONS.map((action) => (
          <Card key={action.key} className="surface-card section-card action-card" variant="borderless">
            <div className="section-head">
              <div>
                <Title level={4} className="section-title">
                  {action.title}
                </Title>
                <Text type="secondary">{action.description}</Text>
              </div>
            </div>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={running === action.key}
              onClick={() => void trigger(action.key)}
            >
              立即执行
            </Button>
          </Card>
        ))}
      </div>

      <Card className="surface-card section-card" variant="borderless">
        <div className="section-head">
          <div>
            <Title level={4} className="section-title">
              <SyncOutlined /> 最近一次结果
            </Title>
            <Text type="secondary">执行完任何操作后，这里会保留最近一次返回摘要。</Text>
          </div>
        </div>
        {lastResult ? (
          <pre className="code-block">{JSON.stringify(lastResult, null, 2)}</pre>
        ) : (
          <Paragraph className="analysis-suggestion">尚未执行任何手动操作。</Paragraph>
        )}
      </Card>
    </div>
  );
}
