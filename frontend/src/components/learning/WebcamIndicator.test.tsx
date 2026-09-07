import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { WebcamIndicator } from "./WebcamIndicator";
import { useWebcamStore } from "@/stores/webcam-store";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode; [key: string]: unknown }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const initialState = {
  mode: "behavioral" as const,
  calibrated: false,
};

describe("WebcamIndicator", () => {
  beforeEach(() => {
    useWebcamStore.setState(initialState);
  });

  describe("adaptive mode", () => {
    beforeEach(() => {
      useWebcamStore.setState({ mode: "adaptive" });
    });

    it("shows 'Adaptive mode active' label", () => {
      render(<WebcamIndicator />);
      expect(screen.getByText("Adaptive mode active")).toBeInTheDocument();
    });
  });

  describe("behavioral mode", () => {
    beforeEach(() => {
      useWebcamStore.setState({ mode: "behavioral" });
    });

    it("shows 'Behavioral mode' label", () => {
      render(<WebcamIndicator />);
      expect(screen.getByText("Behavioral mode")).toBeInTheDocument();
    });
  });

  describe("error mode", () => {
    beforeEach(() => {
      useWebcamStore.setState({ mode: "error" });
    });

    it("shows 'Switched to behavioral mode' label", () => {
      render(<WebcamIndicator />);
      expect(screen.getByText("Switched to behavioral mode")).toBeInTheDocument();
    });

    describe("auto-dismiss after 5 seconds", () => {
      beforeEach(() => {
        vi.useFakeTimers();
      });

      afterEach(() => {
        vi.useRealTimers();
      });

      it("transitions to behavioral mode after 5000ms", () => {
        render(<WebcamIndicator />);
        expect(screen.getByText("Switched to behavioral mode")).toBeInTheDocument();

        act(() => {
          vi.advanceTimersByTime(5000);
        });

        expect(useWebcamStore.getState().mode).toBe("behavioral");
      });

      it("shows 'Behavioral mode' label after 5000ms timeout", () => {
        render(<WebcamIndicator />);

        act(() => {
          vi.advanceTimersByTime(5000);
        });

        expect(screen.getByText("Behavioral mode")).toBeInTheDocument();
      });

      it("does not auto-dismiss before 5000ms", () => {
        render(<WebcamIndicator />);

        act(() => {
          vi.advanceTimersByTime(4999);
        });

        expect(screen.getByText("Switched to behavioral mode")).toBeInTheDocument();
      });

      it("clears the timeout when component unmounts in error mode", () => {
        const setModeSpy = vi.fn();
        useWebcamStore.setState({ mode: "error", setMode: setModeSpy } as Parameters<typeof useWebcamStore.setState>[0]);

        const { unmount } = render(<WebcamIndicator />);
        unmount();

        act(() => {
          vi.advanceTimersByTime(5000);
        });

        // setMode should not have been called after unmount
        expect(setModeSpy).not.toHaveBeenCalled();
      });
    });
  });

  describe("expand on mouseEnter", () => {
    beforeEach(() => {
      useWebcamStore.setState({ mode: "adaptive" });
    });

    it("does not show Settings link before hover", () => {
      render(<WebcamIndicator />);
      expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    });

    it("shows Settings link after mouseEnter", () => {
      render(<WebcamIndicator />);
      const container = screen.getByText("Adaptive mode active").closest(".fixed");
      expect(container).not.toBeNull();
      fireEvent.mouseEnter(container!);
      expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    });

    it("Settings link points at the page that can actually change the setting", () => {
      // Was asserted as `/onboarding?step=webcam`, which pinned a dead link: the wizard reads no
      // `step` param and bounces already-consented learners to `/courses`, so the control this
      // link promised was never reachable. The webcam toggle lives on `/profile`.
      render(<WebcamIndicator />);
      const container = screen.getByText("Adaptive mode active").closest(".fixed");
      fireEvent.mouseEnter(container!);
      expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
        "href",
        "/profile"
      );
    });

    it("hides Settings link after mouseLeave", () => {
      render(<WebcamIndicator />);
      const container = screen.getByText("Adaptive mode active").closest(".fixed");
      fireEvent.mouseEnter(container!);
      expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();

      fireEvent.mouseLeave(container!);
      expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
    });
  });

  describe("behavioral mode expand", () => {
    it("shows Settings link on hover in behavioral mode", () => {
      useWebcamStore.setState({ mode: "behavioral" });
      render(<WebcamIndicator />);
      const container = screen.getByText("Behavioral mode").closest(".fixed");
      fireEvent.mouseEnter(container!);
      expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    });
  });

  describe("mode switching", () => {
    it("updates displayed label when store mode changes", () => {
      useWebcamStore.setState({ mode: "adaptive" });
      render(<WebcamIndicator />);
      expect(screen.getByText("Adaptive mode active")).toBeInTheDocument();

      act(() => {
        useWebcamStore.setState({ mode: "behavioral" });
      });

      expect(screen.getByText("Behavioral mode")).toBeInTheDocument();
    });
  });
});
