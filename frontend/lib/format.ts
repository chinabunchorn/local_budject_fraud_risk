/** Thai formatting helpers — Buddhist-era years arrive as-is from the data. */

export function baht(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("th-TH", { maximumFractionDigits: 2 });
}

/** Compact money for tiles/labels: 2450000 → "2.45 ล้านบาท". */
export function bahtCompact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (Math.abs(n) >= 1_000_000)
    return `${(n / 1_000_000).toLocaleString("th-TH", { maximumFractionDigits: 2 })} ล้านบาท`;
  return `${n.toLocaleString("th-TH", { maximumFractionDigits: 0 })} บาท`;
}

/** Axis-label money: 2450000 → "2.45M" (short, latin — axis ticks only). */
export function bahtAxis(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toLocaleString("en-US", { maximumFractionDigits: 1 })}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toLocaleString("en-US", { maximumFractionDigits: 0 })}k`;
  return String(n);
}

export function pct(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toLocaleString("th-TH", { maximumFractionDigits: digits })}%`;
}

export function fiscalYearTh(y: number): string {
  return `ปีงบประมาณ ${y}`;
}

export function dateTh(iso: string): string {
  return new Date(iso).toLocaleDateString("th-TH", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
