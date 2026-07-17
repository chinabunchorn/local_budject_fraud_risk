"use client";

import Link from "next/link";
import type { EChartsOption } from "echarts";

import { Chart, baseOption } from "@/components/chart";
import { RiskBadge } from "@/components/risk-badge";
import { StatTile } from "@/components/stat-tile";
import { TableTwin } from "@/components/table-twin";
import type { OverviewResponse } from "@/lib/api";
import { bahtCompact } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { RISK_LEVELS, labelInkFor, viz, type RiskLevel } from "@/lib/viz";

const LEVEL_ORDER: RiskLevel[] = ["REQUIRES_INVESTIGATION", "HIGH", "MEDIUM", "LOW"];

function scoreColor(score: number): string {
  const idx = Math.min(
    viz.seq.length - 1,
    Math.max(0, Math.round((score / 100) * (viz.seq.length - 1))),
  );
  return viz.seq[idx];
}

export default function OverviewPage() {
  const { data, error, loading } = useApi<OverviewResponse>("/dashboard/overview");

  if (loading) return <p className="text-muted-foreground">กำลังโหลดข้อมูล…</p>;
  if (error || !data)
    return <p className="text-destructive">โหลดข้อมูลไม่สำเร็จ: {error}</p>;

  const years = [...new Set(data.heatmap.map((c) => c.fiscal_year))].sort();
  const subDistricts = [...new Set(data.heatmap.map((c) => c.sub_district_name_th))];
  const maxCount = Math.max(
    1,
    ...LEVEL_ORDER.map((l) => data.risk_distribution[l] ?? 0),
  );

  const heatmapOption: EChartsOption = {
    ...baseOption(),
    grid: { left: 90, right: 16, top: 8, bottom: 48 },
    xAxis: {
      type: "category",
      data: years.map(String),
      name: "ปีงบประมาณ (พ.ศ.)",
      nameLocation: "middle",
      nameGap: 32,
      nameTextStyle: { color: viz.muted, fontSize: 12 },
      axisLine: { lineStyle: { color: viz.axis } },
      axisTick: { show: false },
      axisLabel: { color: viz.inkSecondary },
    },
    yAxis: {
      type: "category",
      data: subDistricts,
      axisLine: { lineStyle: { color: viz.axis } },
      axisTick: { show: false },
      axisLabel: { color: viz.inkSecondary },
    },
    tooltip: {
      ...baseOption().tooltip,
      formatter: (p) => {
        const params = p as unknown as { value: [number, number, number] };
        const [xi, yi, score] = params.value;
        const cell = data.heatmap.find(
          (c) =>
            c.fiscal_year === years[xi] &&
            c.sub_district_name_th === subDistricts[yi],
        );
        if (!cell) return "";
        const worst = cell.worst_risk_level
          ? RISK_LEVELS[cell.worst_risk_level].labelTh
          : "—";
        return [
          `<strong>${cell.sub_district_name_th}</strong> · ปีงบประมาณ ${cell.fiscal_year}`,
          `คะแนนความเสี่ยงเฉลี่ย: <strong>${score}</strong>`,
          `จำนวนโครงการ: ${cell.project_count}`,
          `งบประมาณรวม: ${bahtCompact(cell.budget_total)}`,
          `ระดับสูงสุดที่พบ: ${worst}`,
        ].join("<br/>");
      },
    },
    series: [
      {
        type: "heatmap",
        itemStyle: { borderColor: viz.surface, borderWidth: 2, borderRadius: 4 },
        label: { show: true, fontSize: 13, fontWeight: 600 },
        emphasis: { itemStyle: { borderColor: viz.surface, borderWidth: 2 } },
        data: data.heatmap.map((c) => {
          const score = c.avg_score ?? 0;
          const fill = scoreColor(score);
          return {
            value: [
              years.indexOf(c.fiscal_year),
              subDistricts.indexOf(c.sub_district_name_th),
              score,
            ],
            itemStyle: { color: fill },
            label: { color: labelInkFor(fill) },
          };
        }),
      },
    ],
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-foreground">ภาพรวมความเสี่ยง</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          ข้อมูลผ่านการประมวลผลและตรวจสอบรูปแบบล่วงหน้า — ไม่มีการเรียกแบบจำลองระหว่างแสดงผล
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="โครงการทั้งหมด"
          value={data.totals.project_count.toLocaleString("th-TH")}
          hint={`${data.totals.sub_district_count} องค์กรปกครองส่วนท้องถิ่น`}
        />
        <StatTile
          label="งบประมาณรวม"
          value={bahtCompact(data.totals.budget_total_sum)}
        />
        <StatTile
          label="ผ่านการวิเคราะห์ความเสี่ยง"
          value={`${data.totals.scored_project_count.toLocaleString("th-TH")} โครงการ`}
        />
        <StatTile
          label="เอกสารประกอบ"
          value={`${data.totals.document_count.toLocaleString("th-TH")} ฉบับ`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <section className="rounded-lg border border-border bg-card p-6 lg:col-span-2">
          <h2 className="font-medium text-foreground">การกระจายระดับความเสี่ยง</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            จำนวนโครงการต่อระดับ (ผลการวิเคราะห์ล่าสุดต่อโครงการ)
          </p>
          <ul className="mt-5 space-y-4">
            {LEVEL_ORDER.map((level) => {
              const count = data.risk_distribution[level] ?? 0;
              const meta = RISK_LEVELS[level];
              return (
                <li key={level}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="inline-flex items-center gap-2 text-foreground">
                      <span
                        className="size-2.5 rounded-full"
                        style={{ backgroundColor: meta.color }}
                        aria-hidden
                      />
                      {meta.labelTh}
                    </span>
                    <span className="tnum font-medium text-foreground">{count}</span>
                  </div>
                  <div className="mt-1.5 h-2 rounded-full bg-muted">
                    <div
                      className="h-2 rounded-full"
                      style={{
                        width: `${(count / maxCount) * 100}%`,
                        backgroundColor: meta.color,
                      }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="rounded-lg border border-border bg-card p-6 lg:col-span-3">
          <h2 className="font-medium text-foreground">
            คะแนนความเสี่ยงเฉลี่ย รายพื้นที่ × ปีงบประมาณ
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            สีเข้มขึ้น = คะแนนเฉลี่ยสูงขึ้น (0–100)
          </p>
          <div className="mt-4">
            <Chart
              option={heatmapOption}
              height={Math.max(180, subDistricts.length * 72 + 70)}
              ariaLabel="แผนภาพความร้อนของคะแนนความเสี่ยงเฉลี่ยรายพื้นที่และปีงบประมาณ"
            />
          </div>
          <TableTwin
            headers={["พื้นที่", "ปีงบประมาณ", "โครงการ", "คะแนนเฉลี่ย", "ระดับสูงสุดที่พบ"]}
            rows={data.heatmap.map((c) => [
              c.sub_district_name_th,
              c.fiscal_year,
              c.project_count,
              c.avg_score ?? "—",
              c.worst_risk_level ? RISK_LEVELS[c.worst_risk_level].labelTh : "—",
            ])}
          />
        </section>
      </div>

      <section className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-6 py-4">
          <h2 className="font-medium text-foreground">
            โครงการที่ควรได้รับความสนใจก่อน
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            เรียงตามระดับความเสี่ยงและคะแนน — การวินิจฉัยขั้นสุดท้ายเป็นของผู้ตรวจสอบ
          </p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="px-6 py-2.5 font-medium">โครงการ</th>
              <th className="px-4 py-2.5 font-medium">พื้นที่</th>
              <th className="px-4 py-2.5 font-medium">ปีงบฯ</th>
              <th className="px-4 py-2.5 text-right font-medium">คะแนน</th>
              <th className="px-6 py-2.5 font-medium">ระดับ</th>
            </tr>
          </thead>
          <tbody>
            {data.top_projects.map((p) => (
              <tr key={p.id} className="border-b border-border last:border-0 hover:bg-muted/40">
                <td className="px-6 py-3">
                  <Link
                    href={`/projects/${p.id}`}
                    className="font-medium text-primary hover:underline"
                  >
                    {p.name_th}
                  </Link>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{p.sub_district_name_th}</td>
                <td className="tnum px-4 py-3">{p.fiscal_year}</td>
                <td className="tnum px-4 py-3 text-right">{p.overall_score.toFixed(1)}</td>
                <td className="px-6 py-3">
                  <RiskBadge level={p.risk_level} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
