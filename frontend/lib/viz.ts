/**
 * Chart palette + chrome — validated instance of the dataviz method on the
 * white surface (validate_palette.js: categorical pair PASS on #ffffff).
 * Charts reference these roles; UI chrome uses the CSS tokens in globals.css.
 */

export const viz = {
  surface: "#ffffff",
  // Categorical slots, fixed order (slot 1 blue, slot 2 green) — never cycled
  series: ["#2a78d6", "#008300"] as const,
  // Sequential blue ramp 100→700 (magnitude: heatmap). Light end = near zero.
  seq: [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
    "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
  ] as const,
  // Status palette (fixed, never themed) — always paired with a text label
  status: {
    good: "#0ca30c",
    warning: "#fab219",
    serious: "#ec835a",
    critical: "#d03b3b",
  },
  ink: "#1c1c1c",
  inkSecondary: "#52514e",
  muted: "#898781",
  grid: "#e9e8e3",
  axis: "#c3c2b7",
  deEmphasis: "#c9c8c2",
} as const;

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "REQUIRES_INVESTIGATION";

/** Verdict enum → Thai label + status color (labels mirror shared/schemas). */
export const RISK_LEVELS: Record<
  RiskLevel,
  { labelTh: string; color: string; rank: number }
> = {
  LOW: { labelTh: "ต่ำ", color: viz.status.good, rank: 1 },
  MEDIUM: { labelTh: "ปานกลาง", color: viz.status.warning, rank: 2 },
  HIGH: { labelTh: "สูง", color: viz.status.serious, rank: 3 },
  REQUIRES_INVESTIGATION: {
    labelTh: "ควรตรวจสอบเพิ่มเติม",
    color: viz.status.critical,
    rank: 4,
  },
};

export const FACTOR_LABELS_TH: Record<string, string> = {
  BUDGET_DEVIATION: "ความเบี่ยงเบนงบประมาณ",
  VENDOR_CONCENTRATION: "การกระจุกตัวของผู้รับจ้าง",
  TIMELINE_ANOMALY: "ความผิดปกติด้านระยะเวลา",
  THRESHOLD_SPLITTING: "การแบ่งซื้อแบ่งจ้าง",
  DOCUMENT_COMPLETENESS: "ความครบถ้วนของเอกสาร",
};

export const STEP_LABELS_TH: Record<string, string> = {
  EVIDENCE: "หลักฐาน",
  OBSERVATION: "ข้อสังเกต",
  INTERPRETATION: "การตีความ",
};

export const PRECHECK_LABELS_TH: Record<string, string> = {
  reference_price_cross_check: "ตรวจทานราคากลาง (บก.01 / เอกสารสัญญา)",
  boq_vs_bk01_total: "ยอดรวม BOQ เทียบ บก.01",
  reference_within_budget: "ราคากลางเทียบวงเงินงบประมาณ",
  contract_within_reference: "ราคาสัญญาเทียบราคากลาง",
  bid_competition: "การแข่งขันในการเสนอราคา",
  procurement_threshold: "เกณฑ์วงเงินของวิธีจัดซื้อจัดจ้าง",
  expected_documents: "เอกสารประกอบตามวิธีจัดซื้อจัดจ้าง",
  yoy_budget_anomaly: "งบประมาณโครงการต่อเนื่องรายปี",
};

export const PRECHECK_STATUS_TH: Record<
  string,
  { labelTh: string; color: string | null }
> = {
  OK: { labelTh: "เป็นไปตามเกณฑ์", color: viz.status.good },
  WARN: { labelTh: "ควรพิจารณา", color: viz.status.warning },
  FLAG: { labelTh: "พบข้อสังเกต", color: viz.status.serious },
  NA: { labelTh: "ข้อมูลไม่เพียงพอ", color: null },
};

export const PROCUREMENT_METHOD_TH: Record<string, string> = {
  E_BIDDING: "ประกวดราคาอิเล็กทรอนิกส์ (e-Bidding)",
  SELECTION: "คัดเลือก",
  SPECIFIC: "เฉพาะเจาะจง",
};

/** Pick in-cell label ink by fill luminance (heatmap cells). */
export function labelInkFor(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 145 ? viz.ink : "#ffffff";
}
