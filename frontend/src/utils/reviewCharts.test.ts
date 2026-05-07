import { describe, expect, it } from "vitest";
import { buildPriceChartOption, hasCandlestickData } from "./reviewCharts";

describe("buildPriceChartOption", () => {
  it("builds an ECharts candlestick option with MA overlays", () => {
    const option = buildPriceChartOption([
      {
        trade_date: "20260421",
        trade_label: "04-21",
        open: 10.1,
        high: 10.8,
        low: 9.9,
        close: 10.5,
        ma5: 10.2,
        ma10: 10.0,
        ma20: 9.8,
        support: 9.7,
        resistance: 10.9,
      },
      {
        trade_date: "20260422",
        trade_label: "04-22",
        open: 10.4,
        high: 11.1,
        low: 10.2,
        close: 10.9,
        ma5: 10.4,
        ma10: 10.1,
        ma20: 9.9,
        support: 9.7,
        resistance: 10.9,
      },
    ]);

    expect(option.xAxis.data).toEqual(["04-21", "04-22"]);
    expect(option.series[0].type).toBe("candlestick");
    expect(option.series[0].data).toEqual([
      [10.1, 10.5, 9.9, 10.8],
      [10.4, 10.9, 10.2, 11.1],
    ]);
    expect(option.series[1].name).toBe("MA5");
    expect(option.series[2].name).toBe("MA10");
    expect(option.series[3].name).toBe("MA20");
    expect(option.series[4]?.markLine?.data).toEqual([{ yAxis: 9.7, name: "支撑" }]);
    expect(option.series[5]?.markLine?.data).toEqual([{ yAxis: 10.9, name: "压力" }]);
  });
});

describe("hasCandlestickData", () => {
  it("returns false when legacy price chart points do not include OHLC", () => {
    expect(
      hasCandlestickData([
        {
          trade_date: "20260421",
          trade_label: "04-21",
          close: 10.5,
          ma5: 10.2,
          ma10: 10.0,
          ma20: 9.8,
          support: 9.7,
          resistance: 10.9,
        } as never,
      ]),
    ).toBe(false);
  });
});
