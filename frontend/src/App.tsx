import { App as AntApp, Button, Drawer, Layout, Menu, Space, Tag, Typography, message } from "antd";
import {
  ApiOutlined,
  BellOutlined,
  ControlOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FundProjectionScreenOutlined,
  KeyOutlined,
  LineChartOutlined,
  NotificationOutlined,
  ProfileOutlined,
} from "@ant-design/icons";
import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { getApiSettings, getAuthEventName, saveApiSettings, type ApiSettings } from "./api/client";
import { ConnectionPanel } from "./components/ConnectionPanel";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { ApiSettingsContext } from "./context/ApiSettingsContext";
import { ControlCenterPage } from "./pages/ControlCenterPage";
import { ClearedPositionsPage } from "./pages/ClearedPositionsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { NewsPage } from "./pages/NewsPage";
import { NotificationCenterPage } from "./pages/NotificationCenterPage";
import { OperationsPage } from "./pages/OperationsPage";
import { PortfolioView } from "./pages/PortfolioView";
import { ReviewPage } from "./pages/ReviewPage";
import { TradeListPage } from "./pages/TradeListPage";

const { Header, Content } = Layout;
const { Title, Text } = Typography;

const menuItems = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "总览" },
  { key: "/trades", icon: <LineChartOutlined />, label: "交易记录" },
  { key: "/portfolio", icon: <FundProjectionScreenOutlined />, label: "持仓" },
  { key: "/review", icon: <ProfileOutlined />, label: "复盘分析" },
  { key: "/news", icon: <NotificationOutlined />, label: "新闻动态" },
  { key: "/notifications", icon: <BellOutlined />, label: "通知中心" },
  { key: "/operations", icon: <DeploymentUnitOutlined />, label: "运行状态" },
  { key: "/control", icon: <ControlOutlined />, label: "操作中心" },
];

function useConnectionState() {
  const [settings, setSettings] = useState<ApiSettings>(() => getApiSettings());

  const update = (next: ApiSettings) => {
    saveApiSettings(next);
    setSettings(next);
  };

  const syncFromStorage = () => {
    setSettings(getApiSettings());
  };

  return { settings, update, syncFromStorage };
}

function ConnectionDrawer({
  open,
  onClose,
  settings,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  settings: ApiSettings;
  onSave: (next: ApiSettings) => void;
}) {
  return (
    <Drawer
      title="接口访问"
      placement="right"
      width={420}
      onClose={onClose}
      open={open}
      destroyOnClose
    >
      <ConnectionPanel settings={settings} onSave={onSave} />
    </Drawer>
  );
}

function Shell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { settings, update, syncFromStorage } = useConnectionState();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const connectionTag = settings.token ? <Tag color="success">已连接</Tag> : <Tag color="warning">未连接</Tag>;
  const isLoginRoute = location.pathname === "/login";

  useEffect(() => {
    const handleAuthStateChanged = (event: Event) => {
      syncFromStorage();
      const authEvent = event as CustomEvent<{ reason?: string }>;
      if (authEvent.detail?.reason === "expired") {
        message.warning("登录状态已过期，请重新登录。");
      }
    };

    window.addEventListener(getAuthEventName(), handleAuthStateChanged as EventListener);
    return () => {
      window.removeEventListener(getAuthEventName(), handleAuthStateChanged as EventListener);
    };
  }, [syncFromStorage]);

  return (
    <ApiSettingsContext.Provider value={{ settings, setSettings: update }}>
      <AntApp>
        <Layout className="app-layout">
          <Header className="app-header">
            <div className="brand-shell">
              <div className="brand-badge">
                <DatabaseOutlined />
              </div>
              <div>
                <Title level={3} className="brand-title">
                  StockAgent
                </Title>
                <Text className="brand-subtitle">
                  交易、持仓、新闻与任务监控
                </Text>
              </div>
            </div>
            <div className="header-actions">
              {!isLoginRoute ? (
                <Menu
                  mode="horizontal"
                  selectedKeys={[location.pathname]}
                  items={menuItems}
                  onClick={({ key }) => navigate(key)}
                  className="top-nav"
                />
              ) : null}
              <Space size={10}>
                {connectionTag}
                {isLoginRoute ? null : (
                  <Button icon={<ApiOutlined />} onClick={() => setDrawerOpen(true)}>
                    接口访问
                  </Button>
                )}
              </Space>
            </div>
          </Header>
          <Content className="app-content">
            <Routes>
              <Route path="/" element={<Navigate to={settings.token ? "/dashboard" : "/login"} replace />} />
              <Route path="/login" element={<LoginPage settings={settings} onSave={update} />} />
              <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
              <Route path="/trades" element={<ProtectedRoute><TradeListPage /></ProtectedRoute>} />
              <Route path="/portfolio" element={<ProtectedRoute><PortfolioView /></ProtectedRoute>} />
              <Route path="/portfolio/cleared" element={<ProtectedRoute><ClearedPositionsPage /></ProtectedRoute>} />
              <Route path="/review" element={<ProtectedRoute><ReviewPage /></ProtectedRoute>} />
              <Route path="/news" element={<ProtectedRoute><NewsPage /></ProtectedRoute>} />
              <Route path="/notifications" element={<ProtectedRoute><NotificationCenterPage /></ProtectedRoute>} />
              <Route path="/operations" element={<ProtectedRoute><OperationsPage /></ProtectedRoute>} />
              <Route path="/control" element={<ProtectedRoute><ControlCenterPage /></ProtectedRoute>} />
            </Routes>
          </Content>
          <ConnectionDrawer
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            settings={settings}
            onSave={update}
          />
        </Layout>
      </AntApp>
    </ApiSettingsContext.Provider>
  );
}

export default function App() {
  return <Shell />;
}
