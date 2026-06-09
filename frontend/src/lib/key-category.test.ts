import { describe, it, expect } from "vitest";
import { categoriseKey } from "./key-category";

describe("categoriseKey", () => {
  describe("category branches (AC #6)", () => {
    it("buckets lowercase letters as alpha", () => {
      expect(categoriseKey("a")).toBe("alpha");
      expect(categoriseKey("z")).toBe("alpha");
    });

    it("buckets uppercase letters as alpha", () => {
      expect(categoriseKey("A")).toBe("alpha");
      expect(categoriseKey("Z")).toBe("alpha");
    });

    it("buckets digits as digit", () => {
      expect(categoriseKey("0")).toBe("digit");
      expect(categoriseKey("9")).toBe("digit");
    });

    it("buckets space and tab as whitespace", () => {
      expect(categoriseKey(" ")).toBe("whitespace");
      expect(categoriseKey("Tab")).toBe("whitespace");
    });

    it("buckets Backspace and Delete as backspace", () => {
      expect(categoriseKey("Backspace")).toBe("backspace");
      expect(categoriseKey("Delete")).toBe("backspace");
    });

    it("buckets Enter as enter", () => {
      expect(categoriseKey("Enter")).toBe("enter");
    });

    it("buckets modifier keys as modifier", () => {
      for (const k of ["Shift", "Control", "Alt", "Meta", "AltGraph"]) {
        expect(categoriseKey(k)).toBe("modifier");
      }
    });

    it("buckets navigation keys as navigation", () => {
      for (const k of [
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
        "PageUp",
        "PageDown",
      ]) {
        expect(categoriseKey(k)).toBe("navigation");
      }
    });

    it("falls back to other for F-keys, dead keys, punctuation, and IME keys", () => {
      expect(categoriseKey("F1")).toBe("other");
      expect(categoriseKey("F12")).toBe("other");
      expect(categoriseKey("Dead")).toBe("other");
      expect(categoriseKey("Process")).toBe("other"); // IME composition
      expect(categoriseKey(".")).toBe("other");
      expect(categoriseKey("@")).toBe("other");
      expect(categoriseKey("Escape")).toBe("other");
    });
  });

  describe("privacy — raw character never leaks (AC #6, Task 2.2)", () => {
    // The privacy guarantee is CONTENT-INDEPENDENCE: the output depends only on
    // the key's *category*, never on which specific letter/digit was pressed. We
    // assert that rather than the story's literal `not.toContain("h")` check,
    // which is impossible because the bucket name "alpha" itself contains "h".
    it("returns the same bucket for different letters (content-independent)", () => {
      expect(categoriseKey("h")).toBe("alpha");
      expect(categoriseKey("q")).toBe("alpha");
      expect(categoriseKey("h")).toBe(categoriseKey("q"));
    });

    it("returns the same bucket for different digits (content-independent)", () => {
      expect(categoriseKey("4")).toBe("digit");
      expect(categoriseKey("7")).toBe("digit");
      expect(categoriseKey("4")).toBe(categoriseKey("7"));
    });

    it("only ever returns one of the fixed category constants", () => {
      const allowed = new Set([
        "alpha",
        "digit",
        "whitespace",
        "backspace",
        "enter",
        "modifier",
        "navigation",
        "other",
      ]);
      for (const ch of "PASSWORD123!@# \tabcXYZ-=Enter") {
        expect(allowed.has(categoriseKey(ch))).toBe(true);
      }
    });
  });
});
