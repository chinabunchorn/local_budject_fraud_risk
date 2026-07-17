/**
 * The table-view twin every chart ships with (WCAG-clean equivalent).
 * Collapsed by default under the chart; numbers align with tabular figures.
 */
export function TableTwin({
  summary = "ดูข้อมูลแบบตาราง",
  headers,
  rows,
}: {
  summary?: string;
  headers: string[];
  rows: (string | number)[][];
}) {
  return (
    <details className="mt-4">
      <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
        {summary}
      </summary>
      <div className="mt-2 overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/60 text-left">
              {headers.map((h) => (
                <th key={h} className="px-3 py-2 font-medium text-muted-foreground">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-border last:border-0">
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className={
                      typeof cell === "number"
                        ? "tnum px-3 py-1.5 text-right"
                        : "px-3 py-1.5"
                    }
                  >
                    {typeof cell === "number" ? cell.toLocaleString("th-TH") : cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
