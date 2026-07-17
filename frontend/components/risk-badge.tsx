import { RISK_LEVELS, type RiskLevel } from "@/lib/viz";

/**
 * Verdict chip: colored dot + Thai label — status color never carries meaning
 * alone. Text stays in ink, per the "text never wears the data color" rule.
 */
export function RiskBadge({
  level,
  size = "sm",
}: {
  level: RiskLevel | null;
  size?: "sm" | "lg";
}) {
  if (!level) {
    return (
      <span className="inline-flex items-center gap-1.5 text-muted-foreground text-sm">
        <span className="size-2 rounded-full bg-border" aria-hidden />
        ยังไม่ได้วิเคราะห์
      </span>
    );
  }
  const meta = RISK_LEVELS[level];
  return (
    <span
      className={
        size === "lg"
          ? "inline-flex items-center gap-2 rounded-md border border-border bg-white px-3 py-1.5 text-base font-medium"
          : "inline-flex items-center gap-1.5 rounded-md border border-border bg-white px-2 py-0.5 text-sm"
      }
    >
      <span
        className={size === "lg" ? "size-3 rounded-full" : "size-2 rounded-full"}
        style={{ backgroundColor: meta.color }}
        aria-hidden
      />
      {meta.labelTh}
    </span>
  );
}
