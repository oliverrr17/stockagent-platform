import { Alert, Space, Tag, Typography } from "antd";

const { Text } = Typography;

type AnalysisPayload = Record<string, unknown>;

export function getAnalysisStatus(payload: AnalysisPayload) {
  const dataSource = String(payload.data_source ?? "未知");
  const degraded = Boolean(payload.degraded);
  const degradedReason = String(payload.degraded_reason ?? "").trim();
  return { dataSource, degraded, degradedReason };
}

export function AnalysisDataStatus({
  payload,
}: {
  payload: AnalysisPayload;
}) {
  const { dataSource, degraded, degradedReason } = getAnalysisStatus(payload);

  return (
    <div className="analysis-status-block">
      <Space wrap>
        <Tag color="blue">数据源：{dataSource}</Tag>
        <Tag color={degraded ? "orange" : "green"}>{degraded ? "降级结果" : "真实结果"}</Tag>
      </Space>
      {degradedReason ? (
        <Alert
          type={degraded ? "warning" : "info"}
          showIcon
          message={degraded ? "当前分析为降级结果" : "当前分析已接入真实数据"}
          description={<Text>{degradedReason}</Text>}
        />
      ) : null}
    </div>
  );
}
