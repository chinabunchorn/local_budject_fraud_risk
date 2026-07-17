"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RiskBadge } from "@/components/risk-badge";
import type { ProjectListResponse } from "@/lib/api";
import { baht } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { PROCUREMENT_METHOD_TH, RISK_LEVELS, type RiskLevel } from "@/lib/viz";

const ALL = "__all__";

export default function ProjectsPage() {
  // Prototype scale (20 projects): fetch once, filter in memory — no refetch flashes.
  const { data, error, loading } = useApi<ProjectListResponse>("/projects");
  const [year, setYear] = useState(ALL);
  const [subDistrict, setSubDistrict] = useState(ALL);
  const [level, setLevel] = useState(ALL);
  const [q, setQ] = useState("");

  const items = useMemo(() => data?.items ?? [], [data]);
  const years = useMemo(
    () => [...new Set(items.map((i) => i.fiscal_year))].sort(),
    [items],
  );
  const subDistricts = useMemo(
    () => [...new Set(items.map((i) => i.sub_district.name_th))],
    [items],
  );

  const filtered = items.filter(
    (i) =>
      (year === ALL || i.fiscal_year === Number(year)) &&
      (subDistrict === ALL || i.sub_district.name_th === subDistrict) &&
      (level === ALL || i.risk_level === level) &&
      (q === "" || i.name_th.includes(q)),
  );

  if (loading) return <p className="text-muted-foreground">กำลังโหลดข้อมูล…</p>;
  if (error || !data)
    return <p className="text-destructive">โหลดข้อมูลไม่สำเร็จ: {error}</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">โครงการทั้งหมด</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          เรียงตามระดับความเสี่ยงและคะแนนจากมากไปน้อย
        </p>
      </div>

      {/* One filter row above everything it scopes */}
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="ค้นหาชื่อโครงการ…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-64"
        />
        <Select value={year} onValueChange={setYear}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>ทุกปีงบประมาณ</SelectItem>
            {years.map((y) => (
              <SelectItem key={y} value={String(y)}>
                ปีงบประมาณ {y}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={subDistrict} onValueChange={setSubDistrict}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>ทุกพื้นที่</SelectItem>
            {subDistricts.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={level} onValueChange={setLevel}>
          <SelectTrigger className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>ทุกระดับความเสี่ยง</SelectItem>
            {(Object.keys(RISK_LEVELS) as RiskLevel[]).map((l) => (
              <SelectItem key={l} value={l}>
                {RISK_LEVELS[l].labelTh}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-sm text-muted-foreground">
          {filtered.length} จาก {data.total} โครงการ
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="px-6 py-3 font-medium">โครงการ</th>
              <th className="px-4 py-3 font-medium">พื้นที่</th>
              <th className="px-4 py-3 font-medium">ปีงบฯ</th>
              <th className="px-4 py-3 text-right font-medium">งบประมาณ (บาท)</th>
              <th className="px-4 py-3 text-right font-medium">ราคาสัญญา (บาท)</th>
              <th className="px-4 py-3 font-medium">วิธีจัดหา</th>
              <th className="px-4 py-3 text-right font-medium">ข้อสังเกต</th>
              <th className="px-4 py-3 text-right font-medium">คะแนน</th>
              <th className="px-6 py-3 font-medium">ระดับ</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <tr key={p.id} className="border-b border-border last:border-0 hover:bg-muted/40">
                <td className="max-w-md px-6 py-3">
                  <Link
                    href={`/projects/${p.id}`}
                    className="font-medium text-primary hover:underline"
                  >
                    {p.name_th}
                  </Link>
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {p.sub_district.name_th}
                </td>
                <td className="tnum px-4 py-3">{p.fiscal_year}</td>
                <td className="tnum px-4 py-3 text-right">{baht(p.budget_total)}</td>
                <td className="tnum px-4 py-3 text-right">{baht(p.contract_price)}</td>
                <td className="px-4 py-3 text-muted-foreground">
                  {p.procurement_method
                    ? (PROCUREMENT_METHOD_TH[p.procurement_method] ?? p.procurement_method)
                    : "—"}
                </td>
                <td className="tnum px-4 py-3 text-right">
                  {p.precheck_flag_count > 0 ? p.precheck_flag_count : "—"}
                </td>
                <td className="tnum px-4 py-3 text-right">
                  {p.overall_score !== null ? p.overall_score.toFixed(1) : "—"}
                </td>
                <td className="px-6 py-3">
                  <RiskBadge level={p.risk_level} />
                </td>
              </tr>
            ))}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-6 py-8 text-center text-muted-foreground">
                  ไม่พบโครงการตามเงื่อนไขที่เลือก
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
