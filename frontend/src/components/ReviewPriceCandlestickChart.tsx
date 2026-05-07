import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { PriceChartPoint } from "../utils/reviewCharts";
import { buildPriceChartOption, hasCandlestickData } from "../utils/reviewCharts";

interface ReviewPriceCandlestickChartProps {
  data: PriceChartPoint[];
}

export function ReviewPriceCandlestickChart({ data }: ReviewPriceCandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || !data.length || !hasCandlestickData(data)) {
      return undefined;
    }

    const chart = echarts.init(element);
    chart.setOption(buildPriceChartOption(data));

    const resizeObserver = new ResizeObserver(() => {
      chart.resize();
    });
    resizeObserver.observe(element);

    return () => {
      resizeObserver.disconnect();
      chart.dispose();
    };
  }, [data]);

  return <div ref={containerRef} className="review-echart-canvas" style={{ width: "100%", height: 320 }} />;
}
