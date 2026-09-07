/**
 * Pipe-delimited text ⇄ the stored `table` block shape.
 *
 * `TableBlock` reads `{ headers: string[], rows: string[][] }`. Authoring that as text keeps the
 * editor small — a lesson uses a table once or twice, which does not justify a resizable grid
 * widget — and keeps the round-trip lossless enough that reopening the editor shows what was
 * typed rather than a reformatted approximation.
 *
 * Kept as pure functions in their own module so the parsing rules are testable without mounting
 * the editor.
 */

export interface TableContent {
  headers: string[];
  rows: string[][];
}

const splitCells = (line: string) => line.split("|").map((cell) => cell.trim());

/**
 * Parse pipe-delimited text. The first non-empty line is the header row.
 *
 * Blank lines are dropped rather than becoming empty rows: a trailing newline is what a textarea
 * gives you for free, and it should not add a row of empty cells to the rendered table.
 */
export function parseTable(text: string): TableContent {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (lines.length === 0) return { headers: [], rows: [] };

  const [headerLine, ...rest] = lines;
  return {
    headers: splitCells(headerLine),
    rows: rest.map(splitCells),
  };
}

/** Render a stored table back to the text form, for editing. */
export function serialiseTable(content: Partial<TableContent> | undefined): string {
  if (!content) return "";
  const headers = content.headers ?? [];
  const rows = content.rows ?? [];
  if (headers.length === 0 && rows.length === 0) return "";

  return [headers, ...rows].map((cells) => cells.join(" | ")).join("\n");
}
