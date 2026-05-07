import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiSettingsContext } from "../context/ApiSettingsContext";
import type { ReviewReport } from "../types";
import { normalizeMissingDataNotes, pickPreferredReportId, ReviewPage } from "./ReviewPage";

const fetchTrades = vi.fn();
const fetchReviewReports = vi.fn();
const generateReviewReport = vi.fn();

vi.mock("../api/trades", () => ({
  fetchTrades: (...args: unknown[]) => fetchTrades(...args),
}));

vi.mock("../api/analysis", () => ({
  fetchReviewReports: (...args: unknown[]) => fetchReviewReports(...args),
  generateReviewReport: (...args: unknown[]) => generateReviewReport(...args),
}));

vi.mock("../components/ReviewPriceCandlestickChart", () => ({
  ReviewPriceCandlestickChart: () => <div>chart</div>,
}));

vi.mock("../components/AnalysisDataStatus", () => ({
  AnalysisDataStatus: () => <div>status</div>,
}));

function renderPage() {
  return render(
    <ApiSettingsContext.Provider
      value={{
        settings: { baseUrl: "http://127.0.0.1:8000", token: "token", refreshToken: "" },
        setSettings: vi.fn(),
      }}
    >
      <ReviewPage />
    </ApiSettingsContext.Provider>,
  );
}

function hasTextContent(expected: string) {
  return (_: string, element: Element | null) => (element?.textContent ?? "").includes(expected);
}

function expectBodyText(text: string) {
  expect(document.body.textContent ?? "").toContain(text);
}

describe("ReviewPage", () => {
  beforeEach(() => {
    fetchTrades.mockReset();
    fetchReviewReports.mockReset();
    generateReviewReport.mockReset();

    fetchTrades.mockResolvedValue([
      {
        id: 58,
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
      },
      {
        id: 1,
        stock_code: "600873",
        stock_name: "Meihua Bio",
        market: "A_STOCK",
        direction: "SELL",
        price: "9.7700",
        quantity: 800,
        commission: "0.0000",
        stamp_duty: "0.0000",
        other_fees: "0.0000",
        trade_time: "2026-04-23T09:39:20+08:00",
        source: "THS",
        created_at: "2026-04-23T10:00:00+08:00",
        intent_snapshot: null,
      },
    ]);

    fetchReviewReports.mockImplementation(async (tradeRecordId?: number) => {
      if (tradeRecordId === 1) {
        return [
          {
            id: 21,
            trade_record: 1,
            report_kind: "llm_coach",
            engine_version: "llm_review_v1",
            version: 1,
            is_latest: true,
            volume_analysis: {},
            chip_analysis: {},
            trend_analysis: {},
            intent_snapshot: null,
            objective_summary: {
              market_heat: "stable",
              industry_heat: "stable",
              company_quality: "average",
            },
            intent_gap_diagnosis: {
              gap_level: "low",
              gap_items: ["execution matched the original plan"],
            },
            subscores: {
              decision_quality: 18,
              context_alignment: 15,
              execution_quality: 14,
              risk_discipline: 13,
              emotion_discipline: 8,
            },
            coach_report_payload: {
              user_intent_summary: "intent not provided",
              objective_context_summary: "meihua report loaded",
              overall_verdict: "meihua report loaded",
              setup_review: "setup review",
              execution_review: "execution review",
              risk_plan_review: "risk review",
              exit_review: "exit review",
              pnl_attribution: "pnl attribution",
              pattern_tag: "sell_review",
              follow_up_advice: "follow the sell-through process",
              next_time_rules: ["confirm the written plan before selling"],
              missing_data_notes: [],
            },
            evidence_payload: {},
            overall_score: 68,
            created_at: "2026-04-25T08:00:00+08:00",
            trade_summary: {
              id: 1,
              stock_code: "600873",
              stock_name: "Meihua Bio",
              market: "A_STOCK",
              direction: "SELL",
              price: "9.7700",
              quantity: 800,
              trade_time: "2026-04-23T09:39:20+08:00",
              source: "THS",
            },
          },
        ];
      }

      return [
        {
          id: 11,
          trade_record: 58,
          report_kind: "llm_coach",
          engine_version: "llm_review_v1",
          version: 2,
          is_latest: true,
          volume_analysis: {},
          chip_analysis: {},
          trend_analysis: {},
          intent_snapshot: null,
          objective_summary: {
            market_heat:
              "market breadth is healthy, northbound flow is positive, and no panic signal is present.",
            industry_heat: "industry strength is mixed but still tradeable.",
            company_quality: "valuation is stretched and profitability is ordinary.",
          },
          intent_gap_diagnosis: {
            gap_level: "medium",
            gap_items: ["the setup was more optimistic than the evidence supported"],
          },
          subscores: {
            decision_quality: 24,
            context_alignment: 16,
            execution_quality: 15,
            risk_discipline: 14,
            emotion_discipline: 8,
          },
          coach_report_payload: {
            user_intent_summary: "trying to trade a breakout",
            objective_context_summary: "the market and industry both held up well.",
            overall_verdict: "the trade thesis was mostly coherent.",
            setup_review: "setup conditions were acceptable.",
            execution_review: "execution was slightly early.",
            risk_plan_review: "risk controls were defined.",
            exit_review: "",
            pnl_attribution: "entry timing was the biggest driver of PnL.",
            pattern_tag: "trend_breakout",
            follow_up_advice: "keep tracking whether industry strength persists.",
            next_time_rules: ["confirm the breakout with volume", "write the stop plan before entering"],
            missing_data_notes: ["intent_snapshot missing because the user did not fill it in."],
          },
          evidence_payload: {},
          overall_score: 77,
          created_at: "2026-04-25T08:00:00+08:00",
          trade_summary: {
            id: 58,
            stock_code: "603063",
            stock_name: "Test Co",
            market: "A_STOCK",
            direction: "BUY",
            price: "40.2800",
            quantity: 200,
            trade_time: "2026-04-24T13:21:17+08:00",
            source: "MANUAL",
          },
        },
      ];
    });
  });

  it("renders score, long objective summaries, and intact missing-data notes", async () => {
    renderPage();

    await waitFor(() => expect(fetchTrades).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fetchReviewReports).toHaveBeenCalledTimes(1));

    await waitFor(() => {
      expectBodyText("the setup was more optimistic than the evidence supported");
      expectBodyText("keep tracking whether industry strength persists.");
      expectBodyText("confirm the breakout with volume");
      expectBodyText("market breadth is healthy, northbound flow is positive, and no panic signal is present.");
      expectBodyText("intent_snapshot missing because the user did not fill it in.");
    });
  }, 20000);

  it("merges character-array missing-data notes into one sentence", () => {
    expect(
      normalizeMissingDataNotes([
        "i",
        "n",
        "t",
        "e",
        "n",
        "t",
        "_",
        "s",
        "n",
        "a",
        "p",
        "s",
        "h",
        "o",
        "t",
        " ",
        "m",
        "i",
        "s",
        "s",
        "i",
        "n",
        "g",
      ]),
    ).toEqual(["intent_snapshot missing"]);
  });

  it("prefers the latest successful report when the newest one is an llm fallback", () => {
    const reports: ReviewReport[] = [
      {
        id: 13,
        trade_record: 29,
        report_kind: "llm_coach",
        engine_version: "llm_review_v1",
        version: 7,
        is_latest: true,
        volume_analysis: {},
        chip_analysis: {},
        trend_analysis: {},
        intent_snapshot: null,
        objective_summary: {
          market_heat: "unknown",
          industry_heat: "unknown",
          company_quality: "unknown",
        },
        intent_gap_diagnosis: {
          gap_level: "low",
          gap_items: [],
        },
        subscores: {
          decision_quality: 0,
          context_alignment: 0,
          execution_quality: 0,
          risk_discipline: 0,
          emotion_discipline: 0,
        },
        coach_report_payload: {
          user_intent_summary: "fallback",
          objective_context_summary: "fallback",
          overall_verdict: "llm unavailable fallback",
          setup_review: "",
          execution_review: "",
          risk_plan_review: "",
          exit_review: "",
          pnl_attribution: "",
          pattern_tag: "fallback",
          follow_up_advice: "fallback",
          next_time_rules: ["fallback"],
          missing_data_notes: ["review_llm_error:ConnectionError"],
        },
        evidence_payload: {},
        overall_score: 68,
        created_at: "2026-04-28T10:00:00+08:00",
        trade_summary: {
          id: 29,
          stock_code: "01712",
          stock_name: "Dragon Resources",
          market: "HK_STOCK",
          direction: "BUY",
          price: "8.2700",
          quantity: 1000,
          trade_time: "2026-04-24T14:23:58+08:00",
          source: "HSBC_EMAIL",
        },
      },
      {
        id: 12,
        trade_record: 29,
        report_kind: "llm_coach",
        engine_version: "llm_review_v1",
        version: 6,
        is_latest: false,
        volume_analysis: {},
        chip_analysis: {},
        trend_analysis: {},
        intent_snapshot: null,
        objective_summary: {
          market_heat: "risk_on",
          industry_heat: "cold",
          company_quality: "good",
        },
        intent_gap_diagnosis: {
          gap_level: "low",
          gap_items: ["old tag set missing"],
        },
        subscores: {
          decision_quality: 18,
          context_alignment: 18,
          execution_quality: 15,
          risk_discipline: 12,
          emotion_discipline: 8,
        },
        coach_report_payload: {
          user_intent_summary: "no subjective intent",
          objective_context_summary: "successful LLM report for Dragon Resources.",
          overall_verdict: "successful report should win",
          setup_review: "",
          execution_review: "",
          risk_plan_review: "",
          exit_review: "",
          pnl_attribution: "",
          pattern_tag: "hk_success",
          follow_up_advice: "successful advice",
          next_time_rules: ["successful rule"],
          missing_data_notes: ["intent snapshot missing."],
        },
        evidence_payload: {},
        overall_score: 30,
        created_at: "2026-04-28T09:00:00+08:00",
        trade_summary: {
          id: 29,
          stock_code: "01712",
          stock_name: "Dragon Resources",
          market: "HK_STOCK",
          direction: "BUY",
          price: "8.2700",
          quantity: 1000,
          trade_time: "2026-04-24T14:23:58+08:00",
          source: "HSBC_EMAIL",
        },
      },
    ];

    expect(pickPreferredReportId(reports)).toBe(12);
  });

  it("switches to the Meihua Bio trade and loads its report", async () => {
    renderPage();

    await waitFor(() => expect(fetchTrades).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fetchReviewReports).toHaveBeenCalledWith(58));

    const select = screen.getByRole("combobox");
    fireEvent.mouseDown(select);
    const option = await screen.findByTitle("600873 · Meihua Bio · 卖出");
    fireEvent.click(option);

    await waitFor(() => expect(fetchReviewReports).toHaveBeenCalledWith(1));
    expectBodyText("meihua report loaded");
  }, 20000);

  it("handles legacy empty reports without crashing when switching trades", async () => {
    fetchReviewReports.mockImplementation(async (tradeRecordId?: number) => {
      if (tradeRecordId === 1) {
        return [
          {
            id: 1,
            trade_record: 1,
            report_kind: "llm_coach",
            engine_version: "llm_review_v1",
            version: 1,
            is_latest: true,
            volume_analysis: {},
            chip_analysis: {},
            trend_analysis: {},
            intent_snapshot: {},
            objective_summary: {},
            intent_gap_diagnosis: {},
            subscores: {},
            coach_report_payload: {},
            evidence_payload: {},
            overall_score: 0,
            created_at: "2026-04-23T10:00:00+08:00",
            trade_summary: {
              id: 1,
              stock_code: "600873",
              stock_name: "Meihua Bio",
              market: "A_STOCK",
              direction: "SELL",
              price: "9.7700",
              quantity: 800,
              trade_time: "2026-04-23T09:39:20+08:00",
              source: "THS",
            },
          },
        ];
      }
      return [];
    });

    renderPage();

    await waitFor(() => expect(fetchTrades).toHaveBeenCalledTimes(1));

    const select = screen.getByRole("combobox");
    fireEvent.mouseDown(select);
    const option = await screen.findByTitle("600873 · Meihua Bio · 卖出");
    fireEvent.click(option);

    await waitFor(() => expect(fetchReviewReports).toHaveBeenCalledWith(1));
    expect(screen.getByRole("alert")).toBeInTheDocument();
  }, 20000);
});
