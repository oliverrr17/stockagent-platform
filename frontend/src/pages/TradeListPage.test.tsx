import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiSettingsContext } from "../context/ApiSettingsContext";
import { TradeListPage } from "./TradeListPage";

const fetchTrades = vi.fn();
const createTrade = vi.fn();
const updateTradeIntentSnapshot = vi.fn();

vi.mock("../api/trades", () => ({
  fetchTrades: (...args: unknown[]) => fetchTrades(...args),
  createTrade: (...args: unknown[]) => createTrade(...args),
  updateTradeIntentSnapshot: (...args: unknown[]) => updateTradeIntentSnapshot(...args),
}));

vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    Modal: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    message: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    },
  };
});

describe("TradeListPage", () => {
  beforeEach(() => {
    fetchTrades.mockReset();
    createTrade.mockReset();
    updateTradeIntentSnapshot.mockReset();
    fetchTrades.mockResolvedValue([]);
    createTrade.mockResolvedValue({
      id: 100,
      stock_code: "603063",
      stock_name: "Test Co",
      market: "A_STOCK",
      direction: "BUY",
      price: "40.2800",
      quantity: 200,
      commission: "0.0000",
      stamp_duty: "0.0000",
      other_fees: "0.0000",
      trade_time: "2026-04-24T13:21:17+08:00",
      source: "MANUAL",
      created_at: "2026-04-25T00:00:00+08:00",
      intent_snapshot: null,
    });
  });

  it("submits a manual trade entry without intent snapshot and refreshes the list", async () => {
    render(
      <ApiSettingsContext.Provider
        value={{
          settings: { baseUrl: "http://127.0.0.1:8000", token: "token", refreshToken: "" },
          setSettings: vi.fn(),
        }}
      >
        <TradeListPage />
      </ApiSettingsContext.Provider>,
    );

    await waitFor(() => expect(fetchTrades).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "manual-trade-open" }));
    fireEvent.change(screen.getByLabelText("manual-stock-code"), { target: { value: "603063" } });
    fireEvent.change(screen.getByLabelText("manual-stock-name"), { target: { value: "Test Co" } });
    fireEvent.change(screen.getByLabelText("manual-market"), { target: { value: "A_STOCK" } });
    fireEvent.change(screen.getByLabelText("manual-direction"), { target: { value: "BUY" } });
    fireEvent.change(screen.getByLabelText("manual-price"), { target: { value: "40.2800" } });
    fireEvent.change(screen.getByLabelText("manual-quantity"), { target: { value: "200" } });
    fireEvent.change(screen.getByLabelText("manual-trade-time"), {
      target: { value: "2026-04-24T13:21:17" },
    });

    fireEvent.click(screen.getByRole("button", { name: "manual-trade-submit" }));

    await waitFor(() => expect(createTrade).toHaveBeenCalledTimes(1));

    const payload = createTrade.mock.calls[0][0];
    expect(payload).toMatchObject({
      stock_code: "603063",
      stock_name: "Test Co",
      market: "A_STOCK",
      direction: "BUY",
      price: "40.2800",
      quantity: 200,
      source: "MANUAL",
      commission: "0",
      stamp_duty: "0",
      other_fees: "0",
    });
    expect(payload.trade_time).toMatch(/^2026-04-24T13:21:17[+-]\d{2}:\d{2}$/);
  }, 20000);

  it("edits intent tags from the row-end editor and saves via patch", async () => {
    fetchTrades.mockResolvedValue([
      {
        id: 101,
        stock_code: "603063",
        stock_name: "Test Co",
        market: "A_STOCK",
        direction: "BUY",
        price: "40.2800",
        quantity: 200,
        commission: "0.0000",
        stamp_duty: "0.0000",
        other_fees: "0.0000",
        trade_time: "2026-04-24T13:21:17+08:00",
        source: "THS",
        created_at: "2026-04-25T00:00:00+08:00",
        intent_snapshot: null,
      },
    ]);
    updateTradeIntentSnapshot.mockResolvedValue({
      id: 101,
      stock_code: "603063",
      stock_name: "Test Co",
      market: "A_STOCK",
      direction: "BUY",
      price: "40.2800",
      quantity: 200,
      commission: "0.0000",
      stamp_duty: "0.0000",
      other_fees: "0.0000",
      trade_time: "2026-04-24T13:21:17+08:00",
      source: "THS",
      created_at: "2026-04-25T00:00:00+08:00",
      intent_snapshot: {
        setup_tags: ["breakout"],
        market_context_tags: ["market_strong"],
        security_quality_tags: [],
        execution_emotion_tags: [],
        overall_notes: "",
        planned_holding_period: "swing",
        planned_stop_loss_type: "",
        planned_stop_loss_value: null,
        planned_take_profit_type: "",
        planned_take_profit_value: null,
      },
    });

    render(
      <ApiSettingsContext.Provider
        value={{
          settings: { baseUrl: "http://127.0.0.1:8000", token: "token", refreshToken: "" },
          setSettings: vi.fn(),
        }}
      >
        <TradeListPage />
      </ApiSettingsContext.Provider>,
    );

    await waitFor(() => expect(fetchTrades).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByLabelText("trade-intent-toggle-101"));
    fireEvent.click(screen.getByLabelText("trade-intent-101-setup-breakout"));
    fireEvent.click(screen.getByLabelText("trade-intent-101-market-market_strong"));
    fireEvent.change(screen.getByLabelText("trade-intent-101-overall-notes"), {
      target: { value: "市场偏强，按突破计划参与。" },
    });
    fireEvent.change(screen.getByLabelText("trade-intent-101-holding-period"), {
      target: { value: "swing" },
    });
    fireEvent.click(screen.getByLabelText("trade-intent-save-101"));

    await waitFor(() => expect(updateTradeIntentSnapshot).toHaveBeenCalledTimes(1));
    expect(updateTradeIntentSnapshot).toHaveBeenCalledWith(101, {
      setup_tags: ["breakout"],
      market_context_tags: ["market_strong"],
      security_quality_tags: [],
      execution_emotion_tags: [],
      overall_notes: "市场偏强，按突破计划参与。",
      planned_holding_period: "swing",
      planned_stop_loss_type: "",
      planned_stop_loss_value: null,
      planned_take_profit_type: "",
      planned_take_profit_value: null,
    });
  }, 20000);
});
