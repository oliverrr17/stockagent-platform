export interface PriceChartPoint {
  trade_date: string;
  trade_label: string;
  open?: number;
  high?: number;
  low?: number;
  close: number;
  ma5: number;
  ma10: number;
  ma20: number;
  support: number;
  resistance: number;
}

export function hasCandlestickData(data: PriceChartPoint[]) {
  return data.every(
    (item) =>
      typeof item.open === "number" &&
      Number.isFinite(item.open) &&
      typeof item.high === "number" &&
      Number.isFinite(item.high) &&
      typeof item.low === "number" &&
      Number.isFinite(item.low) &&
      typeof item.close === "number" &&
      Number.isFinite(item.close),
  );
}

export function buildPriceChartOption(data: PriceChartPoint[]) {
  const lastPoint = data[data.length - 1];

  return {
    animation: false,
    grid: {
      left: 16,
      right: 16,
      top: 24,
      bottom: 24,
      containLabel: true,
    },
    legend: {
      top: 0,
      textStyle: {
        color: "#51606d",
      },
      data: ["K线", "MA5", "MA10", "MA20", "支撑", "压力"],
    },
    tooltip: {
      trigger: "axis",
      axisPointer: {
        type: "cross",
      },
    },
    xAxis: {
      type: "category",
      data: data.map((item) => item.trade_label),
      boundaryGap: true,
      axisLine: {
        lineStyle: {
          color: "rgba(81,96,109,0.32)",
        },
      },
    },
    yAxis: {
      scale: true,
      axisLine: {
        show: false,
      },
      splitLine: {
        lineStyle: {
          color: "rgba(17,100,102,0.08)",
        },
      },
    },
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: data.map((item) => [item.open, item.close, item.low, item.high]),
        itemStyle: {
          color: "#d95d39",
          color0: "#2d6a4f",
          borderColor: "#d95d39",
          borderColor0: "#2d6a4f",
        },
      },
      {
        name: "MA5",
        type: "line",
        data: data.map((item) => item.ma5),
        smooth: true,
        symbol: "none",
        lineStyle: {
          width: 1.5,
          color: "#d8a14d",
        },
      },
      {
        name: "MA10",
        type: "line",
        data: data.map((item) => item.ma10),
        smooth: true,
        symbol: "none",
        lineStyle: {
          width: 1.5,
          color: "#a45f2a",
        },
      },
      {
        name: "MA20",
        type: "line",
        data: data.map((item) => item.ma20),
        smooth: true,
        symbol: "none",
        lineStyle: {
          width: 1.5,
          color: "#51606d",
        },
      },
      {
        name: "支撑",
        type: "line",
        data: [],
        markLine: {
          symbol: "none",
          label: {
            formatter: "支撑",
          },
          lineStyle: {
            type: "dashed",
            color: "#2d6a4f",
          },
          data: lastPoint ? [{ yAxis: lastPoint.support, name: "支撑" }] : [],
        },
      },
      {
        name: "压力",
        type: "line",
        data: [],
        markLine: {
          symbol: "none",
          label: {
            formatter: "压力",
          },
          lineStyle: {
            type: "dashed",
            color: "#b42318",
          },
          data: lastPoint ? [{ yAxis: lastPoint.resistance, name: "压力" }] : [],
        },
      },
    ],
  };
}
