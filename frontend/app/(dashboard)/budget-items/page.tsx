"use client";

import Link from "next/link";
import type { EChartsOption } from "echarts";
import { FileText } from "lucide-react";

import { Chart, baseOption } from "@/components/chart";
import { DocumentViewerDialog, useDocumentViewer } from "@/components/document-viewer";
import { StatTile } from "@/components/stat-tile";
import { TableTwin } from "@/components/table-twin";
import type { BudgetItemGroup, BudgetItemsResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { baht, pct } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { PROCUREMENT_METHOD_TH, viz } from "@/lib/viz";

function findingColor(f: { status: string; values: Record<string, unknown> }): string | null {
  if (f.status === "FLAG") {
    return f.values?.severity === "HIGH" ? viz.status.critical : viz.status.serious;
  }
  if (f.status === "WARN") return viz.status.warning;
  if (f.status === "OK") return viz.status.good;
  return null;
}

function ItemGroupCard({
  group,
  onOpenDocument,
}: {
  group: BudgetItemGroup;
  onOpenDocument: (id: string, filename: string | null, page: number | null) => void;
}) {
  const years = group.years;
  const latest = years[years.length - 1];
  const standard = group.standard;

  const chartOption: EChartsOption = {
    ...baseOption(),
    grid: { left: 64, right: 32, top: 32, bottom: 48 },
    xAxis: {
      type: "category",
      data: years.map((y) => String(y.fiscal_year)),
      name: "ปีงบประมาณ (พ.ศ.)",
      nameLocation: "middle",
      nameGap: 32,
      nameTextStyle: { color: viz.muted, fontSize: 12 },
      axisLine: { lineStyle: { color: viz.axis } },
      axisTick: { show: false },
      axisLabel: { color: viz.inkSecondary },
    },
    yAxis: {
      type: "value",
      name: `บาท/${latest.unit_th ?? "หน่วย"}`,
      nameTextStyle: { color: viz.muted, fontSize: 12 },
      axisLabel: {
        color: viz.muted,
        formatter: (v: number) => v.toLocaleString("en-US"),
      },
      splitLine: { lineStyle: { color: viz.grid, width: 1 } },
    },
    tooltip: {
      ...baseOption().tooltip,
      formatter: (p) => {
        const { dataIndex } = p as unknown as { dataIndex: number };
        const y = years[dataIndex];
        return [
          `<strong>ปีงบประมาณ ${y.fiscal_year}</strong>`,
          `ราคาต่อหน่วย: <strong>${baht(y.unit_price)} บาท/${y.unit_th ?? ""}</strong>`,
          `จำนวน ${y.quantity} ${y.unit_th ?? ""} · รวม ${baht(y.total_amount)} บาท`,
          y.unit_price_yoy_pct !== null
            ? `เทียบปีก่อน: ${pct(y.unit_price_yoy_pct)}`
            : "ปีแรกที่มีข้อมูล",
          y.pct_of_standard !== null
            ? `คิดเป็น ${y.pct_of_standard}% ของราคามาตรฐาน`
            : "",
          y.winner_name ? `ผู้ขาย: ${y.winner_name}` : "",
        ]
          .filter(Boolean)
          .join("<br/>");
      },
    },
    series: [
      {
        type: "bar",
        barWidth: 24,
        itemStyle: { color: viz.series[0], borderRadius: [4, 4, 0, 0] },
        label: {
          show: true,
          position: "top",
          color: viz.ink,
          fontSize: 13,
          formatter: ({ value }) => Number(value).toLocaleString("en-US"),
        },
        data: years.map((y) => y.unit_price),
        // The standard reference price as a labeled threshold line
        markLine: standard
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: viz.status.critical, type: "dashed", width: 1.5 },
              label: {
                position: "insideEndTop",
                color: viz.inkSecondary,
                fontSize: 12,
                formatter: `ราคามาตรฐาน ${standard.standard_unit_price.toLocaleString("en-US")}`,
              },
              data: [{ yAxis: standard.standard_unit_price }],
            }
          : undefined,
      },
    ],
  };

  return (
    <section className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-6 py-4">
        <h2 className="font-medium text-foreground">{group.label_th}</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {group.sub_district_name_th} · ข้อมูลจากรายงานงบประมาณและเอกสารสัญญา (ไม่ใช้แบบจำลอง)
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 px-6 pt-5 lg:grid-cols-4">
        <StatTile
          label={`ราคาต่อหน่วยล่าสุด (ปี ${latest.fiscal_year})`}
          value={`${baht(latest.unit_price)} บาท`}
          hint={
            latest.unit_price_yoy_pct !== null
              ? `${pct(latest.unit_price_yoy_pct)} จากปีก่อน`
              : undefined
          }
        />
        <StatTile
          label="ราคามาตรฐานอ้างอิง"
          value={standard ? `${baht(standard.standard_unit_price)} บาท` : "—"}
          hint={
            standard
              ? `${latest.pct_of_standard ?? "—"}% ของมาตรฐานในปีล่าสุด`
              : "ไม่มีข้อมูลมาตรฐาน"
          }
        />
        <StatTile
          label="ผู้ขายรายล่าสุด"
          value={latest.winner_name ?? "—"}
          hint={
            latest.procurement_method
              ? (PROCUREMENT_METHOD_TH[latest.procurement_method] ??
                latest.procurement_method)
              : undefined
          }
        />
        <StatTile
          label="จำนวนปีที่จัดซื้อ"
          value={`${years.length} ปีงบประมาณ`}
          hint={years.map((y) => y.fiscal_year).join(", ")}
        />
      </div>

      {standard ? (
        <p className="px-6 pt-3 text-xs text-muted-foreground">
          ราคามาตรฐานเป็นข้อมูลที่เจ้าหน้าที่บันทึกจากเอกสารอ้างอิง (
          {standard.provenance === "CURATED" ? "บันทึกโดยเจ้าหน้าที่" : "สกัดอัตโนมัติ"}) —{" "}
          {standard.document_id ? (
            <button
              type="button"
              onClick={() =>
                onOpenDocument(standard.document_id!, standard.filename, standard.page)
              }
              className="font-medium text-primary hover:underline"
            >
              เปิดดูเอกสารต้นฉบับเพื่อตรวจทาน
            </button>
          ) : (
            "ไม่มีเอกสารแนบ"
          )}
        </p>
      ) : null}

      <div className="px-6 pt-4">
        <Chart
          option={chartOption}
          height={280}
          ariaLabel={`กราฟแท่งราคาต่อหน่วยของ${group.label_th}รายปีงบประมาณ เทียบราคามาตรฐาน`}
        />
        <TableTwin
          headers={["ปีงบประมาณ", "จำนวน", "รวม (บาท)", "ราคา/หน่วย (บาท)", "เทียบปีก่อน", "% ของมาตรฐาน"]}
          rows={years.map((y) => [
            y.fiscal_year,
            `${y.quantity} ${y.unit_th ?? ""}`,
            baht(y.total_amount),
            baht(y.unit_price),
            y.unit_price_yoy_pct !== null ? pct(y.unit_price_yoy_pct) : "—",
            y.pct_of_standard !== null ? `${y.pct_of_standard}%` : "—",
          ])}
        />
      </div>

      {group.findings.length > 0 ? (
        <div className="mx-6 mt-5 rounded-md border border-border bg-muted/30 px-4 py-3">
          <h3 className="text-sm font-medium text-foreground">
            ข้อสังเกตจากการตรวจทานเชิงข้อเท็จจริง
          </h3>
          <ul className="mt-2 space-y-2">
            {group.findings.map((f, i) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed">
                <span
                  className="mt-1.5 size-2 shrink-0 rounded-full"
                  style={{ backgroundColor: findingColor(f) ?? "var(--border)" }}
                  aria-hidden
                />
                <span className="text-foreground">
                  {typeof f.values?.justification === "string"
                    ? f.values.justification
                    : f.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-5 border-t border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="px-6 py-2.5 font-medium">ปีงบฯ</th>
              <th className="px-4 py-2.5 font-medium">โครงการ</th>
              <th className="px-4 py-2.5 font-medium">ผู้ขาย</th>
              <th className="px-4 py-2.5 text-right font-medium">ผู้เสนอราคา</th>
              <th className="px-6 py-2.5 font-medium">หลักฐานจำนวน/ยอด</th>
            </tr>
          </thead>
          <tbody>
            {years.map((y) => (
              <tr key={y.fiscal_year} className="border-b border-border align-top last:border-0">
                <td className="tnum px-6 py-3">{y.fiscal_year}</td>
                <td className="max-w-xs px-4 py-3">
                  <Link
                    href={`/projects/${y.project_id}`}
                    className="font-medium text-primary hover:underline"
                  >
                    {y.project_name_th}
                  </Link>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{y.winner_name ?? "—"}</td>
                <td className="tnum px-4 py-3 text-right">{y.bid_count} ราย</td>
                <td className="px-6 py-3">
                  {y.source.document_id ? (
                    <button
                      type="button"
                      onClick={() =>
                        onOpenDocument(
                          y.source.document_id!,
                          y.source.filename,
                          y.source.page,
                        )
                      }
                      className="inline-flex items-center gap-1.5 text-primary hover:underline"
                    >
                      <FileText className="size-3.5 shrink-0" aria-hidden />
                      {y.source.filename}
                      {y.source.page ? ` · หน้า ${y.source.page}` : ""}
                    </button>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                  {y.source.quote_th ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      “{y.source.quote_th}”
                    </p>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function BudgetItemsPage() {
  const { token } = useAuth();
  const { data, error, loading } = useApi<BudgetItemsResponse>("/dashboard/budget-items");
  const viewer = useDocumentViewer();

  if (loading) return <p className="text-muted-foreground">กำลังโหลดข้อมูล…</p>;
  if (error || !data)
    return <p className="text-destructive">โหลดข้อมูลไม่สำเร็จ: {error}</p>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-foreground">
          สรุปการจัดซื้อรายการต่อเนื่อง
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          ติดตามราคาต่อหน่วยของรายการที่จัดซื้อซ้ำข้ามปีงบประมาณ เทียบราคามาตรฐาน —
          จำนวนและยอดเงินสกัดจากเอกสารจริงทุกรายการ (ไม่ใช้แบบจำลองภาษา)
        </p>
      </div>

      {data.items.length === 0 ? (
        <section className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          ยังไม่มีรายการจัดซื้อต่อเนื่องที่ระบบติดตาม
        </section>
      ) : (
        data.items.map((group) => (
          <ItemGroupCard
            key={`${group.sub_district_id}-${group.item_key}`}
            group={group}
            onOpenDocument={viewer.openDocument}
          />
        ))
      )}

      <DocumentViewerDialog
        open={viewer.open}
        onOpenChange={viewer.setOpen}
        documentId={viewer.documentId}
        filename={viewer.filename}
        page={viewer.page}
        token={token}
      />
    </div>
  );
}
