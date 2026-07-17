"use client";

import type { EChartsOption } from "echarts";

import { Chart, baseOption } from "@/components/chart";
import { TableTwin } from "@/components/table-twin";
import type { TrendsResponse } from "@/lib/api";
import { baht, bahtAxis, bahtCompact, pct } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { viz } from "@/lib/viz";

const TOP_CONTRACTORS = 10;

export default function TrendsPage() {
  const { data, error, loading } = useApi<TrendsResponse>("/dashboard/trends");

  if (loading) return <p className="text-muted-foreground">กำลังโหลดข้อมูล…</p>;
  if (error || !data)
    return <p className="text-destructive">โหลดข้อมูลไม่สำเร็จ: {error}</p>;

  const years = [...new Set(data.budget_by_year.map((p) => p.fiscal_year))].sort();
  const subDistricts = [
    ...new Set(data.budget_by_year.map((p) => p.sub_district_name_th)),
  ];

  const lineOption: EChartsOption = {
    ...baseOption(),
    grid: { left: 64, right: 140, top: 24, bottom: 48 },
    legend: {
      top: 0,
      right: 0,
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 12,
      textStyle: { color: viz.inkSecondary },
    },
    xAxis: {
      type: "category",
      data: years.map(String),
      name: "ปีงบประมาณ (พ.ศ.)",
      nameLocation: "middle",
      nameGap: 32,
      nameTextStyle: { color: viz.muted, fontSize: 12 },
      boundaryGap: false,
      axisLine: { lineStyle: { color: viz.axis } },
      axisTick: { show: false },
      axisLabel: { color: viz.inkSecondary },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: viz.muted, formatter: (v: number) => bahtAxis(v) },
      splitLine: { lineStyle: { color: viz.grid, width: 1 } },
    },
    tooltip: {
      ...baseOption().tooltip,
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: viz.axis } },
      formatter: (params) => {
        const list = params as unknown as { seriesName: string; dataIndex: number }[];
        if (!list.length) return "";
        const year = years[list[0].dataIndex];
        const lines = [`<strong>ปีงบประมาณ ${year}</strong>`];
        for (const item of list) {
          const point = data.budget_by_year.find(
            (p) =>
              p.fiscal_year === year &&
              p.sub_district_name_th === item.seriesName,
          );
          if (!point) continue;
          lines.push(
            `${item.seriesName}: <strong>${bahtCompact(point.budget_total)}</strong>` +
              ` (${point.project_count} โครงการ${
                point.yoy_pct !== null ? ` · ${pct(point.yoy_pct)} จากปีก่อน` : ""
              })`,
          );
        }
        return lines.join("<br/>");
      },
    },
    series: subDistricts.map((name, i) => ({
      name,
      type: "line" as const,
      lineStyle: { width: 2, color: viz.series[i] },
      itemStyle: { color: viz.series[i], borderColor: viz.surface, borderWidth: 2 },
      symbol: "circle",
      symbolSize: 9,
      // Direct end-label supplements the legend
      endLabel: {
        show: true,
        color: viz.inkSecondary,
        fontSize: 12,
        formatter: () => name,
        offset: [6, 0],
      },
      data: years.map((y) => {
        const point = data.budget_by_year.find(
          (p) => p.fiscal_year === y && p.sub_district_name_th === name,
        );
        return point?.budget_total ?? null;
      }),
    })),
  };

  const contractors = data.contractor_concentration.slice(0, TOP_CONTRACTORS);
  const barOption: EChartsOption = {
    ...baseOption(),
    grid: { left: 230, right: 80, top: 8, bottom: 40 },
    xAxis: {
      type: "value",
      name: "มูลค่างานที่ชนะ (บาท)",
      nameLocation: "middle",
      nameGap: 28,
      nameTextStyle: { color: viz.muted, fontSize: 12 },
      axisLabel: { color: viz.muted, formatter: (v: number) => bahtAxis(v) },
      splitLine: { lineStyle: { color: viz.grid, width: 1 } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: contractors.map((c) => c.bidder_name_th),
      axisLine: { lineStyle: { color: viz.axis } },
      axisTick: { show: false },
      axisLabel: {
        color: viz.inkSecondary,
        fontSize: 12,
        width: 210,
        overflow: "truncate",
      },
    },
    tooltip: {
      ...baseOption().tooltip,
      formatter: (p) => {
        const { dataIndex } = p as unknown as { dataIndex: number };
        const c = contractors[dataIndex];
        return [
          `<strong>${c.bidder_name_th}</strong>`,
          `มูลค่างานที่ชนะ: <strong>${bahtCompact(c.total_awarded)}</strong>`,
          `ชนะ ${c.contracts_won} จากที่ยื่น ${c.bids_submitted} ครั้ง`,
          `สัดส่วนของมูลค่างานทั้งหมด: ${c.awarded_share_pct ?? 0}%`,
          `ปีงบประมาณที่เกี่ยวข้อง: ${c.fiscal_years.join(", ")}`,
        ].join("<br/>");
      },
    },
    series: [
      {
        type: "bar",
        barWidth: 16,
        itemStyle: { color: viz.series[0], borderRadius: [0, 4, 4, 0] },
        label: {
          show: true,
          position: "right",
          color: viz.ink,
          fontSize: 12,
          formatter: ({ value }) => bahtAxis(Number(value ?? 0)),
        },
        data: contractors.map((c) => c.total_awarded ?? 0),
      },
    ],
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-foreground">แนวโน้มและการกระจุกตัว</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          วิเคราะห์ด้วยฐานข้อมูลโดยตรง (SQL) จากข้อมูลที่สกัดจากเอกสารจริง — ไม่ใช้แบบจำลองภาษา
        </p>
      </div>

      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="font-medium text-foreground">งบประมาณรวมรายปี แยกตามพื้นที่</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          การเพิ่มขึ้นผิดปกติระหว่างปีจะปรากฏใน “ผลการตรวจทานเชิงข้อเท็จจริง” ของโครงการที่เกี่ยวข้อง
        </p>
        <div className="mt-4">
          <Chart
            option={lineOption}
            height={320}
            ariaLabel="กราฟเส้นงบประมาณรวมรายปีงบประมาณ แยกตามพื้นที่"
          />
        </div>
        <TableTwin
          headers={["พื้นที่", "ปีงบประมาณ", "โครงการ", "งบประมาณรวม (บาท)", "เทียบปีก่อน"]}
          rows={data.budget_by_year.map((p) => [
            p.sub_district_name_th,
            p.fiscal_year,
            p.project_count,
            p.budget_total !== null ? baht(p.budget_total) : "—",
            p.yoy_pct !== null ? pct(p.yoy_pct) : "—",
          ])}
        />
      </section>

      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="font-medium text-foreground">
          การกระจุกตัวของผู้รับจ้าง (มูลค่างานที่ชนะ)
        </h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          แสดง {contractors.length} อันดับแรก — ตารางด้านล่างแสดงครบทุกราย
          ข้อมูลนี้เป็นข้อเท็จจริงจากเอกสาร ไม่ใช่ข้อกล่าวอ้างต่อผู้ใด
        </p>
        <div className="mt-4">
          <Chart
            option={barOption}
            height={contractors.length * 36 + 60}
            ariaLabel="กราฟแท่งมูลค่างานที่ผู้รับจ้างแต่ละรายชนะ"
          />
        </div>
        <TableTwin
          headers={[
            "ผู้รับจ้าง",
            "ยื่นข้อเสนอ (ครั้ง)",
            "ชนะ (ครั้ง)",
            "มูลค่างานที่ชนะ (บาท)",
            "สัดส่วน (%)",
            "ปีงบประมาณ",
          ]}
          rows={data.contractor_concentration.map((c) => [
            c.bidder_name_th,
            c.bids_submitted,
            c.contracts_won,
            c.total_awarded !== null ? baht(c.total_awarded) : "—",
            c.awarded_share_pct ?? "—",
            c.fiscal_years.join(", "),
          ])}
        />
      </section>
    </div>
  );
}
