import { LockOutlined } from "@ant-design/icons";
import { Card, Typography } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import { type ApiSettings } from "../api/client";
import { ConnectionPanel } from "../components/ConnectionPanel";

const { Title, Text } = Typography;

export function LoginPage({
  settings,
  onSave,
}: {
  settings: ApiSettings;
  onSave: (next: ApiSettings) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const target = (location.state as { from?: string } | null)?.from || "/dashboard";

  return (
    <div className="login-shell">
      <Card className="surface-card login-card" variant="borderless">
        <div className="login-head">
          <div className="login-icon">
            <LockOutlined />
          </div>
          <div>
            <Title className="page-title">登录</Title>
            <Text className="page-description">登录后即可查看真实交易、持仓、新闻、通知与任务状态。</Text>
          </div>
        </div>
        <ConnectionPanel
          settings={settings}
          onSave={onSave}
          onAuthenticated={() => {
            navigate(target, { replace: true });
          }}
        />
      </Card>
    </div>
  );
}
