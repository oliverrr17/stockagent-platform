import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PortfolioView } from "./PortfolioView";

const fetchPortfolioDashboard = vi.fn();
const fetchPortfolioDailyContributions = vi.fn();

vi.mock("recharts", () => {
  const Container = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Container,
    LineChart: Container,
    CartesianGrid: () => null,
    Line: () => null,
    Tooltip: () => null,
    XAxis: () => null,
    YAxis: () => null,
  };
});

vi.mock("../api/portfolio", () => ({
  fetchPortfolioDashboard: (...args: unknown[]) => fetchPortfolioDashboard(...args),
  fetchPortfolioDailyContributions: (...args: unknown[]) => fetchPortfolioDailyContributions(...args),
  fetchHKTradeHistory: vi.fn(),
  createCashFlow: vi.fn(),
  createManualPosition: vi.fn(),
  deletePosition: vi.fn(),
  updatePosition: vi.fn(),
}));

vi.mock("../context/ApiSettingsContext", () => ({
  useApiSettings: () => ({
    settings: { token: "demo-token" },
  }),
}));

const dashboardPayload = {
  positions: [],
  position_analytics: [],
  overview: {
    base_currency: "CNY" as const,
    start_date: "2026-04-23",
    valuation_date: "2026-05-05",
    audit_status: "FINAL",
    cash_balances: {
      CNY: { balance: 100000, balance_cny: 100000 },
      HKD: { balance: 10000, balance_cny: 8765, fx_rate: 0.8765 },
    },
    positions_market_value_cny: 120000,
    total_assets_cny: 251716.2317,
    realized_pnl_cny: 0,
    unrealized_pnl_cny: 183012.4759,
    total_return_cny: 183012.4759,
    returns: {
      daily: 0.2268,
      monthly: 2.9496,
      yearly: 2.9496,
    },
    curves: {
      daily: [
        {
          date: "2026-05-04",
          total_assets_cny: 251146.682,
          total_return_cny: 182442.9262,
          daily_return_pct: 2.7167,
          cumulative_return_pct: 2.7167,
        },
        {
          date: "2026-05-05",
          total_assets_cny: 251716.2317,
          total_return_cny: 183012.4759,
          daily_return_pct: 0.2268,
          cumulative_return_pct: 2.9496,
        },
      ],
      monthly: [
        {
          date: "2026-05-05",
          total_assets_cny: 251716.2317,
          total_return_cny: 183012.4759,
          daily_return_pct: 0.2268,
          cumulative_return_pct: 2.9496,
        },
      ],
      yearly: [
        {
          date: "2026-05-05",
          total_assets_cny: 251716.2317,
          total_return_cny: 183012.4759,
          daily_return_pct: 0.2268,
          cumulative_return_pct: 2.9496,
        },
      ],
    },
  },
  cash_accounts: [],
  cash_flows: [],
};

const contributionPayload = {
  snapshot_date: "2026-05-05",
  audit_status: "FINAL",
  external_flow_cny: 0,
  computed_daily_pnl_cny: 569.5497,
  contributions: [
    {
      stock_code: "07226",
      stock_name: "South Double Long",
      market: "HK_STOCK",
      start_quantity: 1700,
      end_quantity: 1700,
      previous_close: 3.944,
      latest_price: 3.858,
      trade_cash_delta: 0,
      daily_pnl_native: -146.2,
      daily_pnl_cny: -128.1443,
      fx_rate: 0.8765,
      price_source: "user_verified_manual",
      source_trade_date: "2026-05-05",
      degraded: false,
      degraded_reason: "",
      audit_status: "FINAL",
    },
  ],
};

describe("PortfolioView", () => {
  beforeEach(() => {
    fetchPortfolioDashboard.mockResolvedValue(dashboardPayload);
    fetchPortfolioDailyContributions.mockResolvedValue(contributionPayload);
  });

  it("shows valuation date and audit status in the overview area", async () => {
    render(
      <MemoryRouter>
        <PortfolioView />
      </MemoryRouter>,
    );

    await screen.findByText("2026-05-05");
    expect(screen.getByText("FINAL")).toBeInTheDocument();
  }, 30000);

  it("opens the daily contribution drawer and loads contribution rows", async () => {
    render(
      <MemoryRouter>
        <PortfolioView />
      </MemoryRouter>,
    );

    const button = await screen.findByRole("button", { name: /查看当日收益明细/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(fetchPortfolioDailyContributions).toHaveBeenCalledWith("2026-05-05");
    });
    expect(await screen.findByText("07226")).toBeInTheDocument();
    expect(screen.getByText("South Double Long")).toBeInTheDocument();
  }, 30000);
});
