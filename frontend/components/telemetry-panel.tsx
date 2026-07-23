"use client";

/**
 * Live streaming-performance panel — shows the per-answer telemetry the backend
 * emits (TTFT raw/display, queue wait, tokens/sec, end-to-end). Presentation
 * surface for the Phase-4 optimization story; toggleable so it stays out of the
 * way during a normal Q&A demo.
 */

import { useState } from "react";
import { Activity, ChevronDown } from "lucide-react";

import type { ChatTelemetry } from "@/lib/chat";

function fmt(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : String(Math.round(v));
}

function Tile({
  label,
  value,
  unit,
  hint,
}: {
  label: string;
  value: string;
  unit: string;
  hint?: string;
}) {
  return (
    <div className="rounded-md border border-border bg-white px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 tabular-nums">
        <span className="text-lg font-semibold text-foreground">{value}</span>
        <span className="ml-1 text-[11px] text-muted-foreground">{unit}</span>
      </div>
      {hint ? <div className="mt-0.5 text-[10px] text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

export function TelemetryPanel({ telemetry }: { telemetry: ChatTelemetry }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="mt-3 rounded-lg border border-border bg-secondary/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <span className="flex items-center gap-2 text-xs font-medium text-foreground">
          <Activity className="size-3.5 text-primary" aria-hidden />
          ประสิทธิภาพการสตรีมคำตอบ
        </span>
        <ChevronDown
          className={`size-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="grid grid-cols-2 gap-2 px-3 pb-3 sm:grid-cols-3 lg:grid-cols-5">
          <Tile
            label="TTFT ที่ผู้ใช้เห็น"
            value={fmt(telemetry.ttft_display_ms)}
            unit="ms"
            hint="รวมบัฟเฟอร์ตรวจถ้อยคำ"
          />
          <Tile label="TTFT ดิบ" value={fmt(telemetry.ttft_raw_ms)} unit="ms" hint="โมเดล+ทันเนล" />
          <Tile label="รอคิว vLLM" value={fmt(telemetry.queue_wait_ms)} unit="ms" />
          <Tile
            label="ความเร็วสร้างคำตอบ"
            value={fmt(telemetry.decode_tokens_per_sec)}
            unit="tok/s"
            hint={telemetry.output_tokens ? `${telemetry.output_tokens} โทเคน` : undefined}
          />
          <Tile label="เวลารวม" value={fmt(telemetry.e2e_ms)} unit="ms" />
        </div>
      ) : null}
    </div>
  );
}
