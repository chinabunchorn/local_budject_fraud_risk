"use client";

import type { EChartsOption } from "echarts";
import { FileText } from "lucide-react";

import { Chart, baseOption } from "@/components/chart";
import { DocumentViewerDialog, useDocumentViewer } from "@/components/document-viewer";
import { TableTwin } from "@/components/table-twin";
import type { BudgetReportGroup, BudgetReportTrendsResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { baht, bahtAxis, bahtCompact, pct } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { viz } from "@/lib/viz";

function SubDistrictBudgetCard({
  group,
  onOpenDocument,
}: {
  group: BudgetReportGroup;
  onOpenDocument: (id: string, filename: string | null, page: number | null) => void;
}) {
  const years = group.years;

  // Total budget bars (primary) + project count as a per-bar label; single
  // axis per the dataviz rules. Both metrics also live in the table twin.
  const budgetOption: EChartsOption = {
    ...baseOption(),
    grid: { left: 64, right: 24, top: 24, bottom: 44 },
    xAxis: {
      type: "category",
      data: years.map((y) => String(y.fiscal_year)),
      name: "ปีงบประมาณ (พ.ศ.)",
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: viz.muted, fontSize: 12 },
      axisLine: { lineStyle: { color: viz.axis } },
      axisTick: { show: false },
      axisLabel: { color: viz.inkSecondary },
    },
    yAxis: {
      type: "value",
      name: "บาท",
      nameTextStyle: { color: viz.muted, fontSize: 12 },
      axisLabel: { color: viz.muted, formatter: (v: number) => bahtAxis(v) },
      splitLine: { lineStyle: { color: viz.grid, width: 1 } },
    },
    tooltip: {
      ...baseOption().tooltip,
      formatter: (p) => {
        const { dataIndex } = p as unknown as { dataIndex: number };
        const y = years[dataIndex];
        return [
          `<strong>ปีงบประมาณ ${y.fiscal_year}</strong>`,
          `งบประมาณรวม: <strong>${bahtCompact(y.total_budget)}</strong>`,
          `จำนวนรายการ/โครงการ: ${y.project_count}`,
          y.budget_yoy_pct !== null ? `เทียบปีก่อน: ${pct(y.budget_yoy_pct)}` : "ปีแรกที่มีข้อมูล",
        ].join("<br/>");
      },
    },
    series: [
      {
        type: "bar",
        barWidth: 40,
        itemStyle: { color: viz.series[0], borderRadius: [4, 4, 0, 0] },
        label: {
          show: true,
          position: "top",
          color: viz.inkSecondary,
          fontSize: 12,
          formatter: ({ dataIndex }) =>
            `${bahtAxis(years[dataIndex].total_budget)}\n${years[dataIndex].project_count} รายการ`,
        },
        data: years.map((y) => y.total_budget),
      },
    ],
  };

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-medium text-foreground">{group.sub_district_name_th}</h3>
        <span className="text-xs text-muted-foreground">
          {years.length} ปีงบประมาณ ({years.map((y) => y.fiscal_year).join(", ")})
        </span>
      </div>
      <div className="mt-4">
        <Chart
          option={budgetOption}
          height={300}
          ariaLabel={`กราฟแท่งงบประมาณรวมรายปีของ${group.sub_district_name_th}`}
        />
      </div>
      <TableTwin
        headers={["ปีงบประมาณ", "งบประมาณรวม (บาท)", "จำนวนรายการ", "เทียบปีก่อน", "เอกสารต้นฉบับ"]}
        rows={years.map((y) => [
          y.fiscal_year,
          baht(y.total_budget),
          y.project_count,
          y.budget_yoy_pct !== null ? pct(y.budget_yoy_pct) : "—",
          y.document_filename ?? "—",
        ])}
      />
      <div className="mt-4 border-t border-border pt-4">
        <p className="text-xs text-muted-foreground">เปิดดูรายงานงบประมาณต้นฉบับรายปี:</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {years.map((y) =>
            y.document_id ? (
              <button
                key={y.fiscal_year}
                type="button"
                onClick={() => onOpenDocument(y.document_id!, y.document_filename, null)}
                className="inline-flex items-center gap-1.5 rounded border border-border bg-white px-2 py-1 text-xs text-primary hover:bg-accent"
              >
                <FileText className="size-3.5 shrink-0" aria-hidden />
                {y.document_filename ?? `ปี ${y.fiscal_year}`}
              </button>
            ) : null,
          )}
        </div>
      </div>
    </div>
  );
}

export function BudgetTrendSection() {
  const { token } = useAuth();
  const { data } = useApi<BudgetReportTrendsResponse>("/dashboard/budget-report-trends");
  const viewer = useDocumentViewer();

  if (!data || data.items.length === 0) return null;

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">
          แนวโน้มงบประมาณรายปี (จากรายงานงบประมาณ)
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          งบประมาณรวมและจำนวนรายการต่อปี รวมจากรายการในรายงานงบประมาณของแต่ละตำบล —
          ข้อมูลจากเอกสารจริง ไม่ใช้แบบจำลองภาษา
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        {data.items.map((group) => (
          <SubDistrictBudgetCard
            key={group.sub_district_id}
            group={group}
            onOpenDocument={viewer.openDocument}
          />
        ))}
      </div>
      <DocumentViewerDialog
        open={viewer.open}
        onOpenChange={viewer.setOpen}
        documentId={viewer.documentId}
        filename={viewer.filename}
        page={viewer.page}
        token={token}
      />
    </section>
  );
}
