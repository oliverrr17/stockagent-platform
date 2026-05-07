import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnalysisDataStatus, getAnalysisStatus } from "./AnalysisDataStatus";

describe("AnalysisDataStatus", () => {
  it("extracts status fields from analysis payload", () => {
    expect(
      getAnalysisStatus({
        data_source: "tushare_daily",
        degraded: false,
        degraded_reason: "",
      }),
    ).toEqual({
      dataSource: "tushare_daily",
      degraded: false,
      degradedReason: "",
    });
  });

  it("renders degraded state and reason", () => {
    render(
      <AnalysisDataStatus
        payload={{
          data_source: "fallback_heuristic",
          degraded: true,
          degraded_reason: "港股当前未接入真实趋势数据源，使用降级估算。",
        }}
      />,
    );

    expect(screen.getByText("数据源：fallback_heuristic")).toBeInTheDocument();
    expect(screen.getByText("降级结果")).toBeInTheDocument();
    expect(screen.getByText("当前分析为降级结果")).toBeInTheDocument();
    expect(screen.getByText("港股当前未接入真实趋势数据源，使用降级估算。")).toBeInTheDocument();
  });
});
