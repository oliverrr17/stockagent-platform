import { describe, expect, it } from "vitest";
import { extractReviewMetricEntries } from "./review";

describe("extractReviewMetricEntries", () => {
  it("filters out chart arrays made of objects", () => {
    const metrics = extractReviewMetricEntries({
      volume_signal: "high",
      volume_ratio_20: 1.8234,
      volume_chart: [
        { trade_date: "20260421", volume: 1000 },
        { trade_date: "20260422", volume: 1200 },
      ],
    });

    expect(metrics).toEqual([
      { label: "volume signal", display: "high" },
      { label: "volume ratio 20", display: "1.8234" },
    ]);
  });

  it("keeps scalar arrays such as support levels", () => {
    const metrics = extractReviewMetricEntries({
      support_levels: [9.87],
      resistance_levels: [11.8],
    });

    expect(metrics).toEqual([
      { label: "support levels", display: "9.87" },
      { label: "resistance levels", display: "11.8" },
    ]);
  });
});
