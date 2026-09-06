/**
 * Tests for the table text ⇄ block round-trip.
 *
 * Tables were renderable and unauthorable: `TableBlock` has always drawn them, and no editor tab
 * owned the type, so the only way to author one was to POST the JSON by hand. The parsing is the
 * whole authoring surface, so it is worth pinning — particularly the round-trip, because an
 * author who reopens the editor should see what they typed rather than a reformatting of it.
 */

import { describe, it, expect } from "vitest";

import { parseTable, serialiseTable } from "./table-text";

describe("parseTable", () => {
  it("treats the first line as the header row", () => {
    expect(parseTable("Protocol | Port\nTCP | 6")).toEqual({
      headers: ["Protocol", "Port"],
      rows: [["TCP", "6"]],
    });
  });

  it("trims surrounding whitespace from every cell", () => {
    expect(parseTable("  A  |B\n C |  D  ")).toEqual({
      headers: ["A", "B"],
      rows: [["C", "D"]],
    });
  });

  it("drops blank lines rather than emitting empty rows", () => {
    // A textarea hands you a trailing newline for free; it must not become a row of empty cells.
    expect(parseTable("A | B\nC | D\n\n")).toEqual({
      headers: ["A", "B"],
      rows: [["C", "D"]],
    });
  });

  it("keeps ragged rows as authored", () => {
    // `TableBlock` pads short rows when rendering, so preserving the mistake here means the
    // editor shows the author what they actually wrote.
    expect(parseTable("A | B | C\nD | E")).toEqual({
      headers: ["A", "B", "C"],
      rows: [["D", "E"]],
    });
  });

  it("returns an empty table for empty input", () => {
    expect(parseTable("")).toEqual({ headers: [], rows: [] });
    expect(parseTable("   \n  ")).toEqual({ headers: [], rows: [] });
  });

  it("handles a header-only table", () => {
    expect(parseTable("A | B")).toEqual({ headers: ["A", "B"], rows: [] });
  });
});

describe("serialiseTable", () => {
  it("renders headers and rows back to pipe-delimited text", () => {
    expect(serialiseTable({ headers: ["A", "B"], rows: [["C", "D"]] })).toBe("A | B\nC | D");
  });

  it("returns empty text for a missing or empty table", () => {
    expect(serialiseTable(undefined)).toBe("");
    expect(serialiseTable({})).toBe("");
    expect(serialiseTable({ headers: [], rows: [] })).toBe("");
  });

  it("round-trips through parse without drift", () => {
    const text = "Protocol | Port | Reliable\nTCP | 6 | Yes\nUDP | 17 | No";
    expect(serialiseTable(parseTable(text))).toBe(text);
  });
});
