"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

import { viz } from "@/lib/viz";

/** Base chrome shared by every chart: no animation, Sarabun, hairline solid
 *  grid one shade off the white surface, muted axis ink. */
export function baseOption(): Partial<EChartsOption> {
  return {
    animation: false,
    textStyle: { fontFamily: "Sarabun, system-ui, sans-serif", color: viz.inkSecondary },
    tooltip: {
      backgroundColor: "#ffffff",
      borderColor: viz.grid,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: viz.ink, fontSize: 13, fontFamily: "Sarabun, system-ui, sans-serif" },
      extraCssText: "box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-radius: 6px;",
    },
  };
}

export function Chart({
  option,
  height = 280,
  ariaLabel,
}: {
  option: EChartsOption;
  height?: number;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "svg" });
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  return <div ref={ref} role="img" aria-label={ariaLabel} style={{ height }} />;
}
