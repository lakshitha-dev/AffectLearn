import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useBehavioralSignals } from "./use-behavioral-signals";

describe("useBehavioralSignals", () => {
  describe("return value", () => {
    it("returns { isActive: true } when active=true", () => {
      const { result } = renderHook(() => useBehavioralSignals(true));
      expect(result.current).toEqual({ isActive: true });
    });

    it("returns { isActive: false } when active=false", () => {
      const { result } = renderHook(() => useBehavioralSignals(false));
      expect(result.current).toEqual({ isActive: false });
    });

    it("isActive reflects the active argument directly", () => {
      const { result: r1 } = renderHook(() => useBehavioralSignals(true));
      const { result: r2 } = renderHook(() => useBehavioralSignals(false));
      expect(r1.current.isActive).toBe(true);
      expect(r2.current.isActive).toBe(false);
    });
  });

  describe("return shape", () => {
    it("returns an object with only the isActive property", () => {
      const { result } = renderHook(() => useBehavioralSignals(true));
      expect(Object.keys(result.current)).toEqual(["isActive"]);
    });
  });

  describe("re-render with new active value", () => {
    it("updates isActive when active prop changes from true to false", () => {
      let active = true;
      const { result, rerender } = renderHook(() => useBehavioralSignals(active));
      expect(result.current.isActive).toBe(true);

      active = false;
      rerender();
      expect(result.current.isActive).toBe(false);
    });

    it("updates isActive when active prop changes from false to true", () => {
      let active = false;
      const { result, rerender } = renderHook(() => useBehavioralSignals(active));
      expect(result.current.isActive).toBe(false);

      active = true;
      rerender();
      expect(result.current.isActive).toBe(true);
    });
  });

  describe("no side effects", () => {
    it("does not throw when rendered", () => {
      expect(() => renderHook(() => useBehavioralSignals(true))).not.toThrow();
    });

    it("does not throw when rendered with false", () => {
      expect(() => renderHook(() => useBehavioralSignals(false))).not.toThrow();
    });

    it("can be called multiple times independently", () => {
      const { result: r1 } = renderHook(() => useBehavioralSignals(true));
      const { result: r2 } = renderHook(() => useBehavioralSignals(false));
      const { result: r3 } = renderHook(() => useBehavioralSignals(true));

      expect(r1.current.isActive).toBe(true);
      expect(r2.current.isActive).toBe(false);
      expect(r3.current.isActive).toBe(true);
    });
  });
});
