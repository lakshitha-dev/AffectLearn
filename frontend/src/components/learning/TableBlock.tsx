/**
 * TableBlock — renders a comparison table from a `table` content block.
 *
 * Text blocks are emitted as plain `<p>` paragraphs with no markdown parsing, so a markdown table
 * in lesson copy would render as literal `|` characters. This is the supported way to author
 * tabular material.
 *
 * A real `<table>` (not a grid of divs) so screen readers announce row/column relationships and
 * the content stays selectable and copyable.
 */

export interface TableContent {
  headers?: string[];
  rows?: string[][];
}

export function TableBlock({ content }: { content: TableContent }) {
  const headers = content.headers ?? [];
  const rows = content.rows ?? [];

  // Nothing to show: render nothing rather than an empty bordered box that looks broken.
  if (headers.length === 0 && rows.length === 0) return null;

  // Ragged rows are tolerated by design (the authoring helper does not pad them), so pad to the
  // widest row here — a content typo must not produce a visually broken table.
  const columnCount = Math.max(headers.length, ...rows.map((r) => r.length), 0);

  return (
    // The wrapper scrolls, not the page: a wide table on a narrow screen must never make the
    // whole lesson scroll sideways.
    <div className="my-6 overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        {headers.length > 0 && (
          <thead>
            <tr className="border-b border-border">
              {Array.from({ length: columnCount }, (_, i) => (
                <th
                  key={i}
                  scope="col"
                  className="px-3 py-2 text-left font-semibold text-foreground"
                >
                  {headers[i] ?? ""}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className="border-b border-border/50 last:border-0">
              {Array.from({ length: columnCount }, (_, c) => (
                <td key={c} className="px-3 py-2 align-top text-muted-foreground">
                  {row[c] ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
