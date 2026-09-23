"use client";

import { useEffect, useRef, useState } from "react";
import { CirclePlay, ExternalLink, X } from "lucide-react";

import { apiFetch } from "@/lib/api-client";
import { cn } from "@/lib/cn";
import type { AdaptationVideo } from "@/stores/adaptation-store";

/**
 * "Watch a video explanation" on a confusion card.
 *
 * The learner has read a text hint and may still not see it; a different MEDIUM often helps more
 * than a fourth paragraph. Clicking asks the backend's Video Resource Agent to pick one short
 * YouTube explanation for what this section is about and what the learner got wrong.
 *
 * PRIVACY: nothing is sent to YouTube until the learner clicks, and the player is the
 * `youtube-nocookie.com` embed, which sets no tracking cookies until playback. The lookup itself
 * goes to our backend, never directly from the browser to Google.
 *
 * Never breaks the card: any failure leaves a plain YouTube search link.
 */

export interface VideoHelpResult {
  kind: "embed" | "link";
  url: string;
  videoId?: string | null;
  title?: string | null;
  channel?: string | null;
  durationS?: number | null;
  reason?: string | null;
  throttled?: boolean;
}

interface VideoHelpProps {
  sectionId: string;
  adaptationId?: string;
  /** The hint already on screen, so the agent looks for something other than a repeat. */
  hintText?: string;
  /** Emphasise the button, e.g. after the learner pressed "Still stuck". */
  highlighted?: boolean;
  /**
   * What the Pedagogical agent's Video sub-agent already delivered with a `show_video` card.
   * A ready video renders immediately; `pending` finishes the lookup with the same brief; no
   * value at all (on a `show_video` card) lets the sub-agent write its own query.
   */
  delivered?: AdaptationVideo;
  /** Open without waiting for a click. Set on `show_video` cards, where the video IS the help. */
  autoOpen?: boolean;
}

function deliveredResult(video: AdaptationVideo | undefined): VideoHelpResult | null {
  if (!video || video.pending || !video.kind || !video.url) return null;
  return {
    kind: video.kind,
    url: video.url,
    videoId: video.videoId ?? null,
    title: video.title ?? null,
    channel: video.channel ?? null,
    durationS: video.durationS ?? null,
    reason: video.reason ?? null,
  };
}

type Phase =
  | { name: "idle" }
  | { name: "loading" }
  | { name: "shown"; result: VideoHelpResult }
  | { name: "failed" };

function formatMinutes(seconds: number | null | undefined): string | null {
  if (!seconds || seconds <= 0) return null;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function VideoHelp({
  sectionId,
  adaptationId,
  hintText,
  highlighted,
  delivered,
  autoOpen,
}: VideoHelpProps) {
  const ready = deliveredResult(delivered);
  const [phase, setPhase] = useState<Phase>(
    ready ? { name: "shown", result: ready } : { name: "idle" },
  );
  const openedAt = useRef<number | null>(ready?.kind === "embed" ? Date.now() : null);

  const reportClosed = (videoId: string | null | undefined) => {
    if (openedAt.current === null) return;
    const secondsOpen = (Date.now() - openedAt.current) / 1000;
    openedAt.current = null;
    // 204 No Content: apiFetch always parses JSON, so its rejection here is expected and ignored.
    // Chained from a resolved promise so a synchronous throw is swallowed the same way.
    Promise.resolve()
      .then(() =>
        apiFetch("/learners/me/video-help/closed", {
          method: "POST",
          body: JSON.stringify({ sectionId, videoId: videoId ?? null, secondsOpen }),
        }),
      )
      .catch(() => {});
  };

  // A card replaced by the next one unmounts this with the video still open; record that too.
  useEffect(() => {
    return () => {
      if (phase.name === "shown" && phase.result.kind === "embed") {
        reportClosed(phase.result.videoId);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);

  const open = async () => {
    setPhase({ name: "loading" });
    try {
      const result = await apiFetch<VideoHelpResult>("/learners/me/video-help", {
        method: "POST",
        body: JSON.stringify({
          sectionId,
          adaptationId,
          hintText,
          // The strategist's brief, when the sub-agent ran out of time inside the cycle.
          ...(delivered?.pending && delivered.concept
            ? { concept: delivered.concept, query: delivered.query }
            : {}),
        }),
      });
      if (result.kind === "embed") openedAt.current = Date.now();
      setPhase({ name: "shown", result });
    } catch {
      setPhase({ name: "failed" });
    }
  };

  // A `show_video` card whose video is not ready yet: finish the delegation straight away rather
  // than making the learner click for the very thing the card was sent to show.
  const autoStarted = useRef(false);
  useEffect(() => {
    if (!autoOpen || ready || autoStarted.current) return;
    autoStarted.current = true;
    void open();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoOpen]);

  const close = () => {
    if (phase.name === "shown") reportClosed(phase.result.videoId);
    setPhase({ name: "idle" });
  };

  if (phase.name === "idle" || phase.name === "failed") {
    return (
      <div className="mt-3">
        <button
          type="button"
          onClick={open}
          className={cn(
            "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            highlighted
              ? "bg-red-600 text-white hover:bg-red-700"
              : "border border-border text-foreground hover:bg-border",
          )}
        >
          <CirclePlay
            className={cn("h-4 w-4", highlighted ? "text-white" : "text-red-600")}
            aria-hidden="true"
          />
          Watch a video explanation
        </button>
        {phase.name === "failed" && (
          <p role="alert" className="mt-1 text-xs text-muted-foreground">
            Couldn&apos;t find a video just now. Try again in a moment.
          </p>
        )}
      </div>
    );
  }

  if (phase.name === "loading") {
    return (
      <p role="status" className="mt-3 text-sm text-muted-foreground">
        Finding a good video…
      </p>
    );
  }

  const { result } = phase;

  if (result.kind === "link" || !result.videoId) {
    return (
      <div className="mt-3 flex items-center gap-3">
        <a
          href={result.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          <CirclePlay className="h-4 w-4 text-red-600" aria-hidden="true" />
          Open YouTube search
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
        <button
          type="button"
          onClick={close}
          className="text-xs text-muted-foreground hover:underline"
        >
          Hide
        </button>
      </div>
    );
  }

  const length = formatMinutes(result.durationS);

  return (
    <div className="mt-3 rounded-md border border-border bg-background">
      <div className="flex items-start justify-between gap-2 px-3 pt-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{result.title}</p>
          <p className="text-xs text-muted-foreground">
            {[result.channel, length].filter(Boolean).join(" · ")}
          </p>
        </div>
        <button
          type="button"
          onClick={close}
          aria-label="Close video"
          className="rounded p-1 text-muted-foreground hover:bg-border"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      {result.reason && (
        <p className="px-3 pt-1 text-xs italic text-muted-foreground">{result.reason}</p>
      )}
      <div className="relative mt-2 w-full overflow-hidden rounded-b-md" style={{ paddingTop: "56.25%" }}>
        <iframe
          className="absolute inset-0 h-full w-full"
          src={`https://www.youtube-nocookie.com/embed/${encodeURIComponent(result.videoId)}?rel=0&modestbranding=1`}
          title={result.title ?? "Video explanation"}
          allow="accelerometer; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          referrerPolicy="strict-origin-when-cross-origin"
        />
      </div>
    </div>
  );
}
