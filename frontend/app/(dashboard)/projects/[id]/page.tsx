"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import type { EChartsOption } from "echarts";

import { Chart, baseOption } from "@/components/chart";
import { RiskBadge } from "@/components/risk-badge";
import { StatTile } from "@/components/stat-tile";
import { TableTwin } from "@/components/table-twin";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  type ChunkOut,
  type Citation,
  type FeedbackOut,
  type ProjectDetail,
  type RegulationOut,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { baht, bahtCompact, dateTh } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import {
  FACTOR_LABELS_TH,
  PRECHECK_LABELS_TH,
  PRECHECK_STATUS_TH,
  PROCUREMENT_METHOD_TH,
  STEP_LABELS_TH,
  viz,
} from "@/lib/viz";

function CitationButton({
  citation,
  index,
  onOpen,
}: {
  citation: Citation;
  index: number;
  onOpen: (chunkId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(citation.chunk_id)}
      className="inline-flex items-center gap-1 rounded border border-border bg-white px-1.5 py-0.5 text-xs text-primary hover:bg-accent"
      title="เปิดดูข้อความต้นทางจากเอกสาร"
    >
      อ้างอิง {index + 1}
      {citation.page ? ` · หน้า ${citation.page}` : ""}
    </button>
  );
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const { data, error, loading } = useApi<ProjectDetail>(`/projects/${id}`);
  const { data: feedback, reload: reloadFeedback } = useApi<FeedbackOut[]>(
    `/projects/${id}/feedback`,
  );

  const [chunk, setChunk] = useState<ChunkOut | null>(null);
  const [chunkOpen, setChunkOpen] = useState(false);
  const [regulation, setRegulation] = useState<RegulationOut | null>(null);
  const [regOpen, setRegOpen] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [posting, setPosting] = useState(false);

  async function openChunk(chunkId: string) {
    setChunk(null);
    setChunkOpen(true);
    try {
      setChunk(await api<ChunkOut>(`/chunks/${chunkId}`, token));
    } catch {
      setChunkOpen(false);
    }
  }

  async function openRegulation(code: string) {
    setRegulation(null);
    setRegOpen(true);
    try {
      setRegulation(await api<RegulationOut>(`/regulations/${code}`, token));
    } catch {
      setRegOpen(false);
    }
  }

  async function submitFeedback(e: React.FormEvent) {
    e.preventDefault();
    if (!feedbackText.trim()) return;
    setPosting(true);
    try {
      await api(`/projects/${id}/feedback`, token, {
        method: "POST",
        body: JSON.stringify({
          text_th: feedbackText.trim(),
          risk_result_id: null,
        }),
      });
      setFeedbackText("");
      reloadFeedback();
    } finally {
      setPosting(false);
    }
  }

  if (loading) return <p className="text-muted-foreground">กำลังโหลดข้อมูล…</p>;
  if (error || !data)
    return <p className="text-destructive">โหลดข้อมูลไม่สำเร็จ: {error}</p>;

  const risk = data.risk?.result ?? null;
  const factors = risk
    ? [...risk.factors].sort((a, b) => b.score - a.score)
    : [];

  const factorChart: EChartsOption = {
    ...baseOption(),
    grid: { left: 190, right: 56, top: 8, bottom: 28 },
    xAxis: {
      type: "value",
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: viz.grid, width: 1 } },
      axisLabel: { color: viz.muted },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: factors.map((f) => FACTOR_LABELS_TH[f.factor_type] ?? f.factor_type),
      axisLine: { lineStyle: { color: viz.axis } },
      axisTick: { show: false },
      axisLabel: { color: viz.inkSecondary, fontSize: 13 },
    },
    tooltip: {
      ...baseOption().tooltip,
      formatter: (p) => {
        const { dataIndex } = p as unknown as { dataIndex: number };
        const f = factors[dataIndex];
        return [
          `<strong>${FACTOR_LABELS_TH[f.factor_type] ?? f.factor_type}</strong>`,
          `คะแนน: <strong>${f.score.toFixed(1)}</strong> / 100`,
          `น้ำหนักในการรวมคะแนน: ${(f.weight * 100).toFixed(0)}%`,
        ].join("<br/>");
      },
    },
    series: [
      {
        type: "bar",
        barWidth: 18,
        itemStyle: { color: viz.series[0], borderRadius: [0, 4, 4, 0] },
        label: {
          show: true,
          position: "right",
          color: viz.ink,
          fontSize: 13,
          formatter: ({ value }) => Number(value).toFixed(1),
        },
        data: factors.map((f) => f.score),
      },
    ],
  };

  return (
    <div className="space-y-8">
      <div className="text-sm text-muted-foreground">
        <Link href="/projects" className="text-primary hover:underline">
          โครงการทั้งหมด
        </Link>{" "}
        / รายละเอียดโครงการ
      </div>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-xl font-semibold leading-relaxed text-foreground">
            {data.name_th}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {data.sub_district.name_th} · {data.sub_district.district_th} ·{" "}
            {data.sub_district.province_th} · ปีงบประมาณ {data.fiscal_year}
            {data.procurement_method
              ? ` · ${PROCUREMENT_METHOD_TH[data.procurement_method] ?? data.procurement_method}`
              : ""}
          </p>
        </div>
        <div className="text-right">
          <RiskBadge level={risk?.risk_level ?? null} size="lg" />
          {risk ? (
            <p className="mt-1.5 text-sm text-muted-foreground">
              คะแนนรวม{" "}
              <span className="tnum font-semibold text-foreground">
                {risk.overall_score.toFixed(1)}
              </span>{" "}
              / 100
            </p>
          ) : null}
        </div>
      </div>

      {risk ? (
        <section className="rounded-lg border border-border bg-secondary/60 px-6 py-4">
          <h2 className="text-sm font-medium text-secondary-foreground">
            สรุปผลการวิเคราะห์ (สร้างโดยระบบ)
          </h2>
          <p className="mt-1 text-[15px] leading-relaxed text-foreground">
            {risk.summary_th}
          </p>
        </section>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="วงเงินงบประมาณ" value={bahtCompact(data.budget_total)} />
        <StatTile label="ราคากลาง" value={bahtCompact(data.reference_price)} />
        <StatTile label="ราคาตามสัญญา" value={bahtCompact(data.contract_price)} />
        <StatTile
          label="ประหยัดจากราคากลาง"
          value={
            data.reference_price && data.contract_price
              ? `${(((data.reference_price - data.contract_price) / data.reference_price) * 100).toFixed(1)}%`
              : "—"
          }
        />
      </div>

      {risk ? (
        <section className="rounded-lg border border-border bg-card p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 className="font-medium text-foreground">คะแนนรายปัจจัยความเสี่ยง</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                คะแนนรวมคำนวณแบบกำหนดแน่นอน (deterministic) จากคะแนนรายปัจจัยถ่วงน้ำหนัก
              </p>
            </div>
            <p className="text-xs text-muted-foreground">
              แบบจำลอง {risk.model_id} · ตรวจสอบเมื่อ {dateTh(data.risk!.validated_at)}
            </p>
          </div>
          <div className="mt-4">
            <Chart
              option={factorChart}
              height={factors.length * 44 + 40}
              ariaLabel="กราฟแท่งคะแนนรายปัจจัยความเสี่ยง"
            />
          </div>
          <TableTwin
            headers={["ปัจจัย", "คะแนน", "น้ำหนัก (%)"]}
            rows={factors.map((f) => [
              FACTOR_LABELS_TH[f.factor_type] ?? f.factor_type,
              Number(f.score.toFixed(1)),
              Number((f.weight * 100).toFixed(0)),
            ])}
          />
        </section>
      ) : (
        <section className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          โครงการนี้ยังไม่ผ่านการวิเคราะห์ความเสี่ยงโดยแบบจำลอง
        </section>
      )}

      {risk ? (
        <section className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-6 py-4">
            <h2 className="font-medium text-foreground">
              เส้นทางการให้เหตุผลของแบบจำลอง
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              สร้างโดยแบบจำลองภายใต้โครงสร้างบังคับ (หลักฐาน → ข้อสังเกต → การตีความ)
              และผ่านการตรวจสอบถ้อยคำและการอ้างอิงแล้ว — ไม่ใช่ข้อสรุปของผู้ตรวจสอบ
            </p>
          </div>
          <div className="divide-y divide-border">
            {factors.map((f) => (
              <div key={f.factor_type} className="px-6 py-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="font-medium text-foreground">
                    {FACTOR_LABELS_TH[f.factor_type] ?? f.factor_type}
                  </h3>
                  <span className="tnum text-sm text-muted-foreground">
                    คะแนน {f.score.toFixed(1)} · น้ำหนัก {(f.weight * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="mt-2 text-[15px] leading-relaxed text-foreground">
                  {f.rationale_th}
                </p>
                <ol className="mt-4 space-y-3">
                  {f.reasoning_steps.map((step, i) => (
                    <li key={i} className="flex gap-3">
                      <span className="mt-0.5 inline-flex h-6 shrink-0 items-center rounded border border-border bg-muted px-2 text-xs font-medium text-muted-foreground">
                        {STEP_LABELS_TH[step.step_type] ?? step.step_type}
                      </span>
                      <span className="text-sm leading-relaxed text-foreground">
                        {step.text_th}{" "}
                        {step.citations.map((c, ci) => (
                          <CitationButton
                            key={ci}
                            citation={c}
                            index={ci}
                            onOpen={openChunk}
                          />
                        ))}
                      </span>
                    </li>
                  ))}
                </ol>
                {f.citations.length > 0 ? (
                  <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    เอกสารอ้างอิงของปัจจัยนี้:
                    {f.citations.map((c, ci) => (
                      <CitationButton key={ci} citation={c} index={ci} onOpen={openChunk} />
                    ))}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {risk && risk.regulation_references.length > 0 ? (
        <section className="rounded-lg border border-border bg-card p-6">
          <h2 className="font-medium text-foreground">ข้อกฎหมายที่เกี่ยวข้อง</h2>
          <ul className="mt-4 space-y-3">
            {risk.regulation_references.map((r) => (
              <li
                key={r.regulation_id}
                className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border px-4 py-3"
              >
                <div className="max-w-3xl">
                  <div className="text-sm font-medium text-foreground">
                    {r.act_name_th} · มาตรา/ข้อ {r.section_no}
                  </div>
                  <div className="mt-0.5 text-sm text-muted-foreground">
                    {r.relevance_th}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openRegulation(r.regulation_id)}
                >
                  อ่านบทบัญญัติ
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-6 py-4">
          <h2 className="font-medium text-foreground">
            ผลการตรวจทานเชิงข้อเท็จจริง (คำนวณจากเอกสาร — ไม่ใช้แบบจำลอง)
          </h2>
          {data.prechecks_generated_at ? (
            <p className="mt-0.5 text-xs text-muted-foreground">
              ประมวลผลเมื่อ {dateTh(data.prechecks_generated_at)}
            </p>
          ) : null}
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="px-6 py-2.5 font-medium">รายการตรวจทาน</th>
              <th className="px-4 py-2.5 font-medium">ผล</th>
              <th className="px-6 py-2.5 font-medium">รายละเอียด</th>
            </tr>
          </thead>
          <tbody>
            {data.prechecks.map((c) => {
              const status = PRECHECK_STATUS_TH[c.status] ?? {
                labelTh: c.status,
                color: null,
              };
              const color =
                c.status === "FLAG" && c.severity === "HIGH"
                  ? viz.status.critical
                  : status.color;
              return (
                <tr key={c.name} className="border-b border-border last:border-0 align-top">
                  <td className="px-6 py-3 font-medium text-foreground">
                    {PRECHECK_LABELS_TH[c.name] ?? c.name}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className="size-2 rounded-full"
                        style={{ backgroundColor: color ?? "var(--border)" }}
                        aria-hidden
                      />
                      {status.labelTh}
                      {c.status === "FLAG" && c.severity === "HIGH" ? " (สูง)" : ""}
                    </span>
                  </td>
                  <td className="px-6 py-3 leading-relaxed text-muted-foreground">
                    {c.detail}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-6 py-4">
            <h2 className="font-medium text-foreground">ผู้ยื่นข้อเสนอ</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                <th className="px-6 py-2.5 font-medium">ผู้ยื่น</th>
                <th className="px-4 py-2.5 text-right font-medium">ราคาเสนอ (บาท)</th>
                <th className="px-6 py-2.5 font-medium">ผล</th>
              </tr>
            </thead>
            <tbody>
              {data.bids.map((b) => (
                <tr key={b.bidder_name_th} className="border-b border-border last:border-0">
                  <td className="px-6 py-3">{b.bidder_name_th}</td>
                  <td className="tnum px-4 py-3 text-right">{baht(b.bid_amount)}</td>
                  <td className="px-6 py-3">
                    {b.is_winner ? (
                      <span className="font-medium text-foreground">ผู้ชนะ</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
              {data.bids.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-6 py-6 text-center text-muted-foreground">
                    ไม่มีข้อมูลผู้ยื่นข้อเสนอ
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>

        <section className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-6 py-4">
            <h2 className="font-medium text-foreground">
              เอกสารประกอบ ({data.documents.length} ฉบับ)
            </h2>
          </div>
          <ul className="max-h-72 divide-y divide-border overflow-y-auto text-sm">
            {data.documents.map((d) => (
              <li key={d.id} className="flex items-center justify-between px-6 py-2.5">
                <span className="truncate pr-4">{d.filename}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {d.doc_type ?? d.scope}
                  {d.page_count ? ` · ${d.page_count} หน้า` : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="rounded-lg border border-border bg-card p-6">
        <h2 className="font-medium text-foreground">บันทึกของผู้ตรวจสอบ</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          ความเห็นจะถูกเก็บไว้เพื่อการวิเคราะห์ภาพรวมในรอบถัดไป
        </p>
        <form onSubmit={submitFeedback} className="mt-4 space-y-3">
          <Textarea
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            placeholder="บันทึกข้อสังเกตหรือผลการตรวจสอบเพิ่มเติม…"
            rows={3}
          />
          <Button type="submit" disabled={posting || !feedbackText.trim()}>
            {posting ? "กำลังบันทึก…" : "บันทึกความเห็น"}
          </Button>
        </form>
        <ul className="mt-6 space-y-4">
          {(feedback ?? []).map((f) => (
            <li key={f.id} className="rounded-md border border-border px-4 py-3">
              <div className="flex items-baseline justify-between gap-3 text-xs text-muted-foreground">
                <span>{f.auditor_username}</span>
                <span>{dateTh(f.created_at)}</span>
              </div>
              <p className="mt-1 text-sm leading-relaxed text-foreground">{f.text_th}</p>
            </li>
          ))}
        </ul>
      </section>

      <Dialog open={chunkOpen} onOpenChange={setChunkOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>ข้อความต้นทางจากเอกสาร</DialogTitle>
            <DialogDescription>
              {chunk
                ? `${chunk.document.filename}${chunk.page ? ` · หน้า ${chunk.page}` : ""} · ${chunk.document.doc_type ?? chunk.document.scope}`
                : "กำลังโหลด…"}
            </DialogDescription>
          </DialogHeader>
          {chunk ? (
            <div className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-border bg-muted/40 px-4 py-3 text-sm leading-relaxed">
              {chunk.text}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={regOpen} onOpenChange={setRegOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {regulation
                ? `${regulation.act_name_th} · มาตรา/ข้อ ${regulation.section_no}`
                : "กำลังโหลด…"}
            </DialogTitle>
            {regulation?.section_title_th ? (
              <DialogDescription>{regulation.section_title_th}</DialogDescription>
            ) : null}
          </DialogHeader>
          {regulation ? (
            <div className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border border-border bg-muted/40 px-4 py-3 text-sm leading-relaxed">
              {regulation.text}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
