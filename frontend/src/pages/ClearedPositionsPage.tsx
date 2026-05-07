import { ReloadOutlined } from "@ant-design/icons";
import { Button, Card, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { fetchClearedPositions } from "../api/portfolio";
import { useApiSettings } from "../context/ApiSettingsContext";
import type { PortfolioClearedPosition } from "../types";
import { formatDateTime, marketMeta } from "../utils/display";
import { getApiErrorMessage } from "../utils/errors";

const { Title, Text } = Typography;

function formatMoney(value: number) {
  return Number(value).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function ClearedPositionsPage() {
  const {
    settings: { token },
  } = useApiSettings();
  const [rows, setRows] = useState<PortfolioClearedPosition[]>([]);
  const [loading, setLoading] = useState(false);

  const loadRows = async () => {
    setLoading(true);
    try {
      if (!token) {
        setRows([]);
        return;
      }
      setRows(await fetchClearedPositions());
    } catch (error) {
      message.error(getApiErrorMessage(error, "已清仓股票加载失败。"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRows();
  }, [token]);

  const columns: ColumnsType<PortfolioClearedPosition> = [
    {
      title: "证券",
      key: "stock",
      render: (_, record) => (
        <>
          <div>{record.stock_code}</div>
          <Text type="secondary">{record.stock_name}</Text>
        </>
      ),
    },
    {
      title: "市场",
      key: "market",
      render: (_, record) => <Tag color={marketMeta(record.market).color}>{marketMeta(record.market).label}</Tag>,
    },
    {
      title: "已实现收益(本币)",
      key: "realized_native",
      align: "right",
      render: (_, record) => formatMoney(record.realized_pnl_native),
    },
    {
      title: "已实现收益(CNY)",
      key: "realized_cny",
      align: "right",
      render: (_, record) => formatMoney(record.realized_pnl_cny),
    },
    {
      title: "清仓时间",
      key: "updated_at",
      render: (_, record) => formatDateTime(record.updated_at),
    },
  ];

  return (
    <div className="page-shell">
      <div className="page-header">
        <div>
          <Title className="page-title">已清仓股票</Title>
          <Text className="page-description">保留已清仓股票的收益结果，便于和当前持仓区分查看。</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void loadRows()} loading={loading}>
          刷新
        </Button>
      </div>

      <Card className="surface-card section-card table-card" variant="borderless">
        <Table
          size="small"
          rowKey={(record) => `${record.market}-${record.stock_code}`}
          dataSource={rows}
          columns={columns}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          locale={{ emptyText: <div className="empty-note">暂无已清仓股票。</div> }}
        />
      </Card>
    </div>
  );
}
