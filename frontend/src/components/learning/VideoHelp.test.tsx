import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const apiFetch = vi.fn();
vi.mock("@/lib/api-client", () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { VideoHelp } from "./VideoHelp";

beforeEach(() => {
  apiFetch.mockReset();
});

describe("VideoHelp", () => {
  it("loads nothing from YouTube until clicked", () => {
    render(<VideoHelp sectionId="s1" />);
    expect(apiFetch).not.toHaveBeenCalled();
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("asks the agent and plays the chosen video in the card", async () => {
    apiFetch.mockResolvedValueOnce({
      kind: "embed",
      url: "https://www.youtube.com/watch?v=BBB",
      videoId: "BBB",
      title: "Why range stops early",
      channel: "Y",
      durationS: 300,
      reason: "It shows why range stops before 5.",
    });
    render(<VideoHelp sectionId="s1" adaptationId="a1" hintText="Think about 0." />);
    await userEvent.click(screen.getByRole("button", { name: /watch a video explanation/i }));

    const [path, init] = apiFetch.mock.calls[0];
    expect(path).toBe("/learners/me/video-help");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      sectionId: "s1",
      adaptationId: "a1",
      hintText: "Think about 0.",
    });

    const frame = await screen.findByTitle("Why range stops early");
    expect(frame.getAttribute("src")).toContain("youtube-nocookie.com/embed/BBB");
    expect(screen.getByText("It shows why range stops before 5.")).toBeInTheDocument();
    expect(screen.getByText("Y · 5:00")).toBeInTheDocument();
  });

  it("closing reports how long the video was open", async () => {
    apiFetch
      .mockResolvedValueOnce({ kind: "embed", url: "u", videoId: "BBB", title: "T" })
      .mockResolvedValueOnce(undefined);
    render(<VideoHelp sectionId="s1" />);
    await userEvent.click(screen.getByRole("button", { name: /watch a video explanation/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Close video" }));

    const [path, init] = apiFetch.mock.calls[1];
    expect(path).toBe("/learners/me/video-help/closed");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.videoId).toBe("BBB");
    expect(typeof body.secondsOpen).toBe("number");
    expect(screen.getByRole("button", { name: /watch a video explanation/i })).toBeInTheDocument();
  });

  it("falls back to a YouTube search link", async () => {
    apiFetch.mockResolvedValueOnce({
      kind: "link",
      url: "https://www.youtube.com/results?search_query=range+explained",
    });
    render(<VideoHelp sectionId="s1" />);
    await userEvent.click(screen.getByRole("button", { name: /watch a video explanation/i }));

    const link = await screen.findByRole("link", { name: /open youtube search/i });
    expect(link).toHaveAttribute(
      "href",
      "https://www.youtube.com/results?search_query=range+explained",
    );
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("a failed lookup keeps the button and says so", async () => {
    apiFetch.mockRejectedValueOnce(new Error("boom"));
    render(<VideoHelp sectionId="s1" />);
    await userEvent.click(screen.getByRole("button", { name: /watch a video explanation/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't find a video");
    expect(screen.getByRole("button", { name: /watch a video explanation/i })).toBeInTheDocument();
  });
});

describe("VideoHelp on a show_video card (the Video sub-agent's delivery)", () => {
  it("plays a delivered video immediately, with no lookup", () => {
    render(
      <VideoHelp
        sectionId="s1"
        autoOpen
        delivered={{ kind: "embed", url: "u", videoId: "BBB", title: "Delivered video" }}
      />,
    );
    expect(apiFetch).not.toHaveBeenCalled();
    expect(screen.getByTitle("Delivered video").getAttribute("src")).toContain("/embed/BBB");
  });

  it("finishes a pending delegation with the strategist's brief", async () => {
    apiFetch.mockResolvedValueOnce({ kind: "embed", url: "u", videoId: "CCC", title: "Found" });
    render(
      <VideoHelp
        sectionId="s1"
        autoOpen
        delivered={{ pending: true, concept: "range end value", query: "python range stop" }}
      />,
    );
    expect(await screen.findByTitle("Found")).toBeInTheDocument();
    const body = JSON.parse((apiFetch.mock.calls[0][1] as RequestInit).body as string);
    expect(body.concept).toBe("range end value");
    expect(body.query).toBe("python range stop");
  });
});
