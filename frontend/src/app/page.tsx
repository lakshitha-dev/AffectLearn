"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/session-store";

const ROLE_DASHBOARDS: Record<string, string> = {
  learner: "/courses",
  course_designer: "/analytics",
  admin: "/users",
};

export default function LandingPage() {
  const { accessToken, expiresAt, user } = useSessionStore();
  const router = useRouter();
  const isAuthenticated =
    accessToken !== null && expiresAt !== null && Date.now() < expiresAt;

  useEffect(() => {
    if (isAuthenticated && user) {
      router.replace(ROLE_DASHBOARDS[user.role] ?? "/courses");
    }
  }, [isAuthenticated, user, router]);

  if (isAuthenticated && user) return null;

  return (
    <div className="min-h-screen bg-background text-foreground antialiased selection:bg-foreground selection:text-background">
      {/* ===== Tiny editorial header ===== */}
      <header>
        <div className="mx-auto flex max-w-[1180px] items-baseline justify-between px-6 py-6 text-[13px] md:px-10">
          <Link href="/" className="font-medium tracking-tight">
            AffectLearn
            <span className="ml-2 text-muted">— FYRP, 2026</span>
          </Link>
          <nav className="flex items-baseline gap-7 text-muted">
            <a href="#loop" className="hidden hover:text-foreground md:inline">
              The loop
            </a>
            <a href="#privacy" className="hidden hover:text-foreground md:inline">
              Privacy
            </a>
            <a href="#designers" className="hidden hover:text-foreground md:inline">
              Designers
            </a>
            <Link href="/login" className="text-foreground hover:underline underline-offset-4">
              Sign in →
            </Link>
          </nav>
        </div>
      </header>

      {/* ===== Hero — asymmetric, headline + research log ===== */}
      <section>
        <div className="mx-auto grid max-w-[1180px] grid-cols-1 gap-14 px-6 pt-16 pb-28 md:px-10 lg:grid-cols-12 lg:gap-16 lg:pt-28 lg:pb-40">
          <div className="lg:col-span-8">
            <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
              Adaptive e-learning · final-year research project
            </p>
            <h1 className="mt-8 font-semibold leading-[0.95] tracking-[-0.03em] text-[clamp(2.5rem,8vw,5.75rem)]">
              Course content
              <br />
              that <span className="text-primary">notices</span> when a
              <br />
              learner is{" "}
              <em className="font-serif font-normal italic tracking-tight text-foreground/85">
                losing the thread.
              </em>
            </h1>
            <p className="mt-10 max-w-[34rem] text-[15px] leading-[1.7] text-muted md:text-[16px]">
              <span className="mr-1 font-mono text-foreground/60">*</span>A
              four-agent system that reads facial and behavioral affect in the
              browser, decides whether to intervene, and rewrites the lesson —
              quietly, in place. Webcam frames never leave the device.
            </p>
            <div className="mt-12 flex flex-wrap items-center gap-x-7 gap-y-4 text-sm">
              <Link
                href="/register"
                className="inline-flex items-center gap-2 bg-foreground px-5 py-3 font-medium text-background transition-colors hover:bg-foreground/85"
              >
                Try as a learner
                <span aria-hidden>→</span>
              </Link>
              <Link
                href="/login"
                className="font-medium text-foreground underline decoration-foreground/30 decoration-1 underline-offset-[6px] transition-colors hover:decoration-foreground"
              >
                Sign in as designer
              </Link>
            </div>
          </div>

          <aside className="lg:col-span-4 lg:border-l lg:border-border lg:pl-10">
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
              — Field notes
            </p>
            <ul className="mt-7 space-y-3 font-mono text-[12px] leading-relaxed">
              {[
                ["2026.05", "Onboarding wizard, calibration"],
                ["2026.04", "Designer heatmap dashboard"],
                ["2026.03", "Bi-LSTM behavioral classifier"],
                ["2026.02", "CNN-LSTM facial affect on DAiSEE"],
                ["2026.01", "Four-agent loop · LangGraph"],
                ["2025.12", "Llama 3 LoRA · content adapter"],
                ["2025.11", "Pilot protocol drafted"],
              ].map(([date, label]) => (
                <li
                  key={label}
                  className="grid grid-cols-[64px_1fr] items-baseline gap-4 border-b border-border/60 pb-3 last:border-0"
                >
                  <span className="text-muted">{date}</span>
                  <span className="text-foreground/85">{label}</span>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      </section>

      {/* ===== Affect timeline — full-bleed data strip ===== */}
      <section className="border-y border-border bg-surface">
        <div className="mx-auto max-w-[1180px] px-6 py-14 md:px-10">
          <div className="flex flex-wrap items-baseline justify-between gap-y-2">
            <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
              Sample learner timeline · Module 3, Data Structures
            </p>
            <span className="font-mono text-[11px] text-muted">
              62 min · 4 sections · webcam + behavioral
            </span>
          </div>

          <AffectTimeline />

          <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[11px] text-muted">
            <Swatch className="bg-affect-engaged">engaged</Swatch>
            <Swatch className="bg-affect-confused">confused</Swatch>
            <Swatch className="bg-affect-bored">bored</Swatch>
            <Swatch className="bg-affect-frustrated">frustrated</Swatch>
            <span className="ml-auto hidden text-muted/70 sm:inline">
              ↑ Two adaptations triggered at the confusion stretch
            </span>
          </div>
        </div>
      </section>

      {/* ===== The agent loop ===== */}
      <section id="loop">
        <div className="mx-auto max-w-[1180px] px-6 py-24 md:px-10 lg:py-32">
          <div className="grid gap-14 lg:grid-cols-[1fr_1.7fr] lg:gap-20">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
                — The loop
              </p>
              <h2 className="mt-4 text-[clamp(1.875rem,3.5vw,2.75rem)] font-semibold leading-[1.05] tracking-tight">
                Four agents,
                <br />
                running every{" "}
                <span className="font-mono text-primary">30s</span>.
              </h2>
              <p className="mt-6 max-w-md text-[15px] leading-[1.7] text-muted">
                The pipeline runs on the server while the learner reads.
                Decisions arrive in under a second — and most of the time the
                decision is to do nothing, because the learner is fine.
              </p>
            </div>

            <AgentLoop />
          </div>
        </div>
      </section>

      {/* ===== Privacy stance — full bleed black band ===== */}
      <section id="privacy" className="bg-secondary text-background">
        <div className="mx-auto max-w-[1180px] px-6 py-24 md:px-10 lg:py-32">
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-background/45">
            — Privacy stance
          </p>
          <h2 className="mt-5 max-w-4xl text-[clamp(1.875rem,4.5vw,3.5rem)] font-semibold leading-[1.05] tracking-tight">
            No frame of webcam video is uploaded, written to disk, or kept after
            the agent decides.
          </h2>
          <div className="mt-14 grid gap-10 text-[14px] leading-[1.75] text-background/70 sm:grid-cols-3">
            <PrivacyPoint label="On-device">
              MediaPipe extracts feature vectors in the browser. Only those
              vectors — not pixels — leave the device.
            </PrivacyPoint>
            <PrivacyPoint label="No retention">
              Server-side, the vectors are consumed by the agent loop and
              discarded. They are never persisted.
            </PrivacyPoint>
            <PrivacyPoint label="Optional">
              Learners can decline the webcam entirely. The behavioral Bi-LSTM
              still works on interaction signals alone.
            </PrivacyPoint>
          </div>
        </div>
      </section>

      {/* ===== For designers — heatmap with the project's real modules ===== */}
      <section id="designers">
        <div className="mx-auto max-w-[1180px] px-6 py-24 md:px-10 lg:py-32">
          <div className="grid items-center gap-16 lg:grid-cols-2 lg:gap-20">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
                — For course designers
              </p>
              <h2 className="mt-4 text-[clamp(1.875rem,3.5vw,2.75rem)] font-semibold leading-[1.05] tracking-tight">
                Find the paragraph that loses the cohort.
              </h2>
              <p className="mt-6 max-w-lg text-[15px] leading-[1.7] text-muted">
                The dashboard aggregates affect across the cohort and surfaces a
                confusion or boredom hotspot per section. Click in and you see
                exactly which content block triggered it — so you rewrite what
                matters, not the whole module.
              </p>
              <Link
                href="/login"
                className="mt-10 inline-flex items-center gap-2 font-medium text-foreground underline decoration-foreground/30 decoration-1 underline-offset-[6px] transition-colors hover:decoration-foreground"
              >
                Sign in to the dashboard
                <span aria-hidden>→</span>
              </Link>
            </div>

            <Heatmap />
          </div>
        </div>
      </section>

      {/* ===== Closing ===== */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-[1180px] px-6 py-24 text-center md:px-10 lg:py-32">
          <h2 className="text-[clamp(1.875rem,4.5vw,3.5rem)] font-semibold leading-[1.05] tracking-tight">
            Open the platform.
          </h2>
          <p className="mx-auto mt-5 max-w-md text-[15px] leading-[1.7] text-muted">
            A learner account takes a minute. Designer and admin accounts are
            pre-provisioned — credentials appear on the sign-in page during the
            pilot.
          </p>
          <div className="mt-12 flex items-center justify-center gap-x-7 gap-y-4 text-sm">
            <Link
              href="/register"
              className="inline-flex items-center gap-2 bg-foreground px-5 py-3 font-medium text-background transition-colors hover:bg-foreground/85"
            >
              Create a learner account
              <span aria-hidden>→</span>
            </Link>
            <Link
              href="/login"
              className="font-medium text-foreground underline decoration-foreground/30 decoration-1 underline-offset-[6px] transition-colors hover:decoration-foreground"
            >
              Sign in
            </Link>
          </div>
        </div>
      </section>

      {/* ===== Minimal footer ===== */}
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[1180px] items-baseline justify-between px-6 py-7 text-[12px] text-muted md:px-10">
          <span>AffectLearn — School of Computing, {new Date().getFullYear()}</span>
          <span className="font-mono">v0.1 · pre-pilot</span>
        </div>
      </footer>
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* Sub-components                                                            */
/* ------------------------------------------------------------------------ */

function Swatch({
  className,
  children,
}: {
  className: string;
  children: React.ReactNode;
}) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-2.5 w-2.5 ${className}`} />
      {children}
    </span>
  );
}

function PrivacyPoint({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <span className="block font-mono text-[10px] uppercase tracking-[0.22em] text-background/40">
        — {label}
      </span>
      <p className="mt-3">{children}</p>
    </div>
  );
}

/* ---------- Affect timeline (deterministic sequence, 4 sections) ---------- */

type AffectKind = "engaged" | "confused" | "bored" | "frustrated";

const TIMELINE: AffectKind[] = [
  // 3.1 Arrays — mostly engaged (~16 min)
  ...Array<AffectKind>(11).fill("engaged"),
  "bored",
  ...Array<AffectKind>(4).fill("engaged"),
  // 3.2 Linked Lists — confusion stretch + adaptation (~16 min)
  ...Array<AffectKind>(3).fill("engaged"),
  ...Array<AffectKind>(5).fill("confused"),
  "frustrated",
  "confused",
  "engaged", // ← adaptation lands
  ...Array<AffectKind>(2).fill("engaged"),
  "bored",
  ...Array<AffectKind>(2).fill("engaged"),
  // 3.3 Binary Trees — second confusion + adaptation (~15 min)
  ...Array<AffectKind>(2).fill("engaged"),
  "confused",
  "confused",
  "engaged", // ← second adaptation
  ...Array<AffectKind>(8).fill("engaged"),
  "bored",
  "engaged",
  "engaged",
  // 3.4 Hash Tables — finish strong (~15 min)
  ...Array<AffectKind>(12).fill("engaged"),
  "confused",
  "engaged",
  "engaged",
];

// Section ranges through the timeline, in order. Sums to TIMELINE.length.
const TIMELINE_SECTIONS: Array<{ count: number; label: string }> = [
  { count: 16, label: "3.1 Arrays" },
  { count: 16, label: "3.2 Linked Lists" },
  { count: 16, label: "3.3 Binary Trees" },
  { count: 15, label: "3.4 Hash Tables" },
];

const KIND_CLASS: Record<AffectKind, string> = {
  engaged: "bg-affect-engaged",
  confused: "bg-affect-confused",
  bored: "bg-affect-bored",
  frustrated: "bg-affect-frustrated",
};

function AffectTimeline() {
  return (
    <div className="mt-8">
      <div className="flex items-end gap-[3px]">
        {TIMELINE.map((kind, i) => (
          <div
            key={i}
            className={`h-10 flex-1 transition-opacity hover:opacity-70 ${KIND_CLASS[kind]}`}
            title={`min ${i + 1}: ${kind}`}
          />
        ))}
      </div>
      <div
        className="mt-3 grid gap-[3px] font-mono text-[11px] text-muted"
        style={{
          gridTemplateColumns: TIMELINE_SECTIONS.map((s) => `${s.count}fr`).join(" "),
        }}
      >
        {TIMELINE_SECTIONS.map((s) => (
          <span key={s.label} className="truncate">
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ---------- Agent loop diagram (4 horizontal nodes) ---------- */

const AGENTS = [
  {
    n: "01",
    name: "Affect detector",
    body: "Fuses facial CNN-LSTM and behavioral Bi-LSTM into a confidence-weighted state vector.",
  },
  {
    n: "02",
    name: "Learner profiler",
    body: "Updates a rolling profile — recent confusion, fatigue, comprehension trend.",
  },
  {
    n: "03",
    name: "Pedagogical strategist",
    body: "Picks an intervention class: simplify, hint, encourage, suggest break, do nothing.",
  },
  {
    n: "04",
    name: "Content adapter",
    body: "Generates the adaptation via Llama 3 LoRA and emits it over the websocket.",
  },
];

function AgentLoop() {
  return (
    <ol className="grid gap-px overflow-hidden border border-border bg-border md:grid-cols-2 xl:grid-cols-4">
      {AGENTS.map((a, i) => (
        <li
          key={a.n}
          className="relative flex flex-col bg-background p-7 transition-colors hover:bg-surface"
        >
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-[11px] text-primary">{a.n}</span>
            {i < AGENTS.length - 1 && (
              <span
                aria-hidden
                className="hidden font-mono text-[11px] text-muted xl:inline"
              >
                →
              </span>
            )}
          </div>
          <h3 className="mt-5 text-[15px] font-semibold tracking-tight text-foreground">
            {a.name}
          </h3>
          <p className="mt-2 text-[13px] leading-[1.7] text-muted">{a.body}</p>
        </li>
      ))}
    </ol>
  );
}

/* ---------- Heatmap (real-feel, no chrome) ---------- */

const HEATMAP = [
  { label: "3.1 Arrays", values: [78, 12, 8, 2] },
  { label: "3.2 Linked Lists", values: [45, 38, 7, 10] },
  { label: "3.3 Binary Trees", values: [62, 24, 9, 5] },
  { label: "3.4 Hash Tables", values: [38, 41, 14, 7] },
];

const HEATMAP_KINDS: AffectKind[] = ["engaged", "confused", "bored", "frustrated"];

function Heatmap() {
  const tint = (kind: AffectKind, v: number) => {
    const opacity = Math.min(0.9, Math.max(0.08, v / 100));
    return `rgb(var(--affect-${kind}) / ${opacity})`;
  };

  return (
    <div className="border border-border">
      <div className="grid grid-cols-[1.3fr_repeat(4,1fr)] font-mono text-[11px]">
        <div className="border-b border-border bg-surface px-4 py-3 text-muted">
          Section
        </div>
        {HEATMAP_KINDS.map((k) => (
          <div
            key={k}
            className="border-b border-l border-border bg-surface px-3 py-3 text-center text-muted"
          >
            {k}
          </div>
        ))}
        {HEATMAP.map((row, rIdx) => (
          <HeatmapRow
            key={row.label}
            row={row}
            tint={tint}
            isLast={rIdx === HEATMAP.length - 1}
          />
        ))}
      </div>
      <p className="border-t border-border bg-surface px-4 py-3 font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
        — Cohort of 24 · last 7 days
      </p>
    </div>
  );
}

function HeatmapRow({
  row,
  tint,
  isLast,
}: {
  row: { label: string; values: number[] };
  tint: (k: AffectKind, v: number) => string;
  isLast: boolean;
}) {
  const border = isLast ? "" : "border-b border-border";
  return (
    <>
      <div className={`${border} px-4 py-3 font-mono text-[12px] text-foreground`}>
        {row.label}
      </div>
      {row.values.map((v, i) => (
        <div
          key={i}
          className={`${border} border-l border-border px-2 py-3 text-center`}
        >
          <span
            className="inline-block min-w-[2.5rem] px-1.5 py-0.5 font-mono text-[12px] text-foreground"
            style={{ backgroundColor: tint(HEATMAP_KINDS[i], v) }}
          >
            {v}%
          </span>
        </div>
      ))}
    </>
  );
}
