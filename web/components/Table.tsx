// Plain numeric tables: the accessible version of each chart, and the reference tables.
// They scroll inside their own box, never the page.

export type Column = {
  label: React.ReactNode;
  /** numbers align right (the default); text columns left */
  align?: "left" | "right";
};

export type Row = {
  key: string;
  /** the first cell is the row's header (a year, month or name) */
  cells: React.ReactNode[];
  /** a muted row, e.g. a partial year or a forecast */
  muted?: boolean;
};

export function Table({
  caption,
  columns,
  rows,
  minWidth = "28rem",
  captionVisible = false,
}: {
  caption: string;
  columns: Column[];
  rows: Row[];
  minWidth?: string;
  captionVisible?: boolean;
}) {
  const align = (c: Column | undefined, i: number) =>
    (c?.align ?? (i === 0 ? "left" : "right")) === "left" ? "text-left" : "text-right";
  // Columns marked "left" hold text and wrap within a readable width (min-width has no
  // effect on a table cell itself, so it goes on a block inside it); the rest are numbers,
  // years or months and never wrap.
  const text = (i: number) => columns[i]?.align === "left";
  const numeric = (i: number) => (text(i) ? "" : "num");
  const content = (cell: React.ReactNode, i: number) =>
    text(i) ? <span className="block min-w-44">{cell}</span> : cell;
  return (
    <div className="table-scroll border-y border-line">
      <table className="w-full border-collapse text-sm" style={{ minWidth }}>
        <caption
          className={captionVisible ? "pt-2 pb-3 text-left text-xs text-muted" : "sr-only"}
        >
          {caption}
        </caption>
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            {columns.map((c, i) => (
              <th
                key={i}
                scope="col"
                className={`px-2 py-2 align-bottom font-normal first:pl-0 last:pr-0 ${align(c, i)}`}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.key}
              className={`border-b border-line last:border-b-0 ${r.muted ? "text-muted" : ""}`}
            >
              {r.cells.map((cell, i) =>
                i === 0 ? (
                  <th
                    key={i}
                    scope="row"
                    className={`py-1.5 pr-2 font-normal ${numeric(i)} ${align(columns[i], i)}`}
                  >
                    {content(cell, i)}
                  </th>
                ) : (
                  <td
                    key={i}
                    className={`px-2 py-1.5 last:pr-0 ${numeric(i)} ${align(columns[i], i)}`}
                  >
                    {content(cell, i)}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A chart's numbers, folded away under the chart until the reader opens them. */
export function NumbersTable({
  summary = "the numbers behind this chart",
  ...props
}: React.ComponentProps<typeof Table> & { summary?: string }) {
  return (
    <details className="mt-5 text-sm">
      <summary className="cursor-pointer text-muted hover:text-fg">{summary}</summary>
      <div className="mt-3">
        <Table {...props} />
      </div>
    </details>
  );
}
