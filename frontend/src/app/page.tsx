"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/session-store";
import "./landing.css";

const ROLE_DASHBOARDS: Record<string, string> = {
  learner: "/courses",
  course_designer: "/analytics",
  admin: "/users",
};

/* ------------------------------------------------------------------ */
/* Inline icon set (stroke icons mirror the reference)                 */
/* ------------------------------------------------------------------ */

type IconProps = { className?: string };
const s = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const ArrowRight = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} strokeWidth={2.4} {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);
const PlayCircle = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} strokeWidth={2.2} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M10 8.5l5 3.5-5 3.5z" fill="currentColor" stroke="none" />
  </svg>
);
const Shield = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} strokeWidth={2.2} {...p}>
    <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);
const Lock = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} strokeWidth={2.2} {...p}>
    <rect x="3" y="11" width="18" height="10" rx="2" />
    <path d="M7 11V8a5 5 0 0110 0v3" />
  </svg>
);
const Activity = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} strokeWidth={2.2} {...p}>
    <path d="M4 12h4l3 8 4-16 3 8h2" />
  </svg>
);
const Bulb = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <path d="M9 18h6M10 22h4" />
    <path d="M12 2a7 7 0 00-4 12.7c.6.5 1 1.2 1 2h6c0-.8.4-1.5 1-2A7 7 0 0012 2z" />
  </svg>
);
const Bolt = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <path d="M13 2L3 14h7l-1 8 10-12h-7z" />
  </svg>
);
const Clock = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v4l3 2" />
  </svg>
);
const Eye = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);
const ClockSimple = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
);
const Trend = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <path d="M4 17l6-6 4 4 6-7" />
    <path d="M20 8v4h-4" />
  </svg>
);
const Alert = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v4M12 16h.01" />
  </svg>
);
const Layout = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <rect x="3" y="4" width="18" height="14" rx="2" />
    <path d="M3 9h18M8 18v3M16 18v3" />
  </svg>
);
const Check = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <path d="M20 6L9 17l-5-5" />
  </svg>
);
const CheckBold = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} strokeWidth={2.4} {...p}>
    <path d="M20 6L9 17l-5-5" />
  </svg>
);
const Refresh = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} strokeWidth={2.2} {...p}>
    <path d="M21 12a9 9 0 11-3-6.7L21 8" />
    <path d="M21 3v5h-5" />
  </svg>
);
const UrlLock = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4}>
    <rect x="4" y="10" width="16" height="10" rx="2" />
    <path d="M8 10V7a4 4 0 018 0v3" />
  </svg>
);
const EyeOff = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <path d="M2 2l20 20M9.5 9.5a3 3 0 004 4" />
    <path d="M6.7 6.7A9.8 9.8 0 002 12s3.5 7 10 7a9.7 9.7 0 005.3-1.7M9 4.6A9.9 9.9 0 0112 4c6.5 0 10 8 10 8a18 18 0 01-2.2 3.2" />
  </svg>
);
const UserPlus = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21v-1a6 6 0 0112 0v1" />
    <path d="M18 8h4M20 6v4" />
  </svg>
);
const ShieldPlain = (p: IconProps) => (
  <svg viewBox="0 0 24 24" {...s} {...p}>
    <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
  </svg>
);
const Plus = (p: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" {...p}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);
const TOAST_ICONS = { bulb: Bulb, bolt: Bolt, clock: Clock } as const;

/* ------------------------------------------------------------------ */
/* Animated affect panel state cycle (hero mockup)                     */
/* ------------------------------------------------------------------ */

type ToastSpec = { ic: keyof typeof TOAST_ICONS; t: string; p: string; ac: string; abg: string };
type AffectState = {
  name: string;
  hint: string;
  color: string;
  bg: string;
  bars: [number, number, number];
  keys: [string, string, string];
  showHint: boolean;
  prog: number;
  toast: ToastSpec | null;
};

// The states the DEPLOYED gate can act on, plus the resting state.
//
// A fourth entry, "Frustrated", used to cycle here with a break suggestion. No model in the
// system detects frustration — it was dropped from the adaptation vocabulary precisely because
// listing it implied a capability that does not exist — so animating it on the front page was
// the most prominent unsupported claim we made. `--frustrated` stays defined in the stylesheet
// for the research monitor, which still charts the label.
const STATES: AffectState[] = [
  { name: "Engaged", hint: "Keeping pace — nice work", color: "var(--engaged)", bg: "rgba(22,163,74,.12)", bars: [80, 12, 8], keys: ["Engaged", "Confused", "Bored"], showHint: false, prog: 64, toast: null },
  { name: "Confused", hint: "Lingering on a tough idea", color: "var(--confused)", bg: "rgba(217,119,6,.12)", bars: [16, 74, 10], keys: ["Confused", "Engaged", "Bored"], showHint: true, prog: 66, toast: { ic: "bulb", t: "Hint ready", p: "Here's a simpler way to see it.", ac: "var(--brand)", abg: "var(--tint)" } },
  { name: "Bored", hint: "Attention drifting from this page", color: "var(--bored)", bg: "rgba(100,116,139,.16)", bars: [72, 16, 12], keys: ["Bored", "Engaged", "Confused"], showHint: false, prog: 88, toast: { ic: "bolt", t: "Move on?", p: "You've stalled here — jump to the next part.", ac: "var(--brand)", abg: "var(--tint)" } },
];

function HeroMock() {
  const [idx, setIdx] = useState(0);
  const [toastOn, setToastOn] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setIdx((i) => (i + 1) % STATES.length), 2800);
    return () => clearInterval(id);
  }, []);

  // re-trigger the toast slide-in whenever the state changes
  useEffect(() => {
    const st = STATES[idx];
    if (!st.toast) {
      setToastOn(false);
      return;
    }
    setToastOn(false);
    const t = setTimeout(() => setToastOn(true), 180);
    return () => clearTimeout(t);
  }, [idx]);

  const st = STATES[idx];
  const ToastIcon = st.toast ? TOAST_ICONS[st.toast.ic] : null;
  const nameColor = st.color === "var(--engaged)" ? "var(--ink)" : st.color;

  return (
    <div className="mock reveal in d2" aria-hidden="true">
      <div className="mock-glow" />
      <div className={`htoast${toastOn ? " show" : ""}`}>
        <div className="ti" style={st.toast ? { background: st.toast.abg, color: st.toast.ac } : undefined}>
          {ToastIcon ? <ToastIcon /> : <Bulb />}
        </div>
        <div>
          <strong>{st.toast?.t ?? "Hint ready"}</strong>
          <p>{st.toast?.p ?? "Here's a simpler way to see it."}</p>
        </div>
      </div>

      <div className="browser">
        <div className="browser-bar">
          <div className="traffic">
            <i />
            <i />
            <i />
          </div>
          <div className="url">
            <UrlLock /> app.affectlearn.com/lesson
          </div>
        </div>
        <div className="app">
          <div className="lesson">
            <div className="crumb">Network Fundamentals · Lesson 3</div>
            <h3>The TCP/IP Handshake</h3>
            <div className="lprog">
              <div className="ptrack">
                <i style={{ width: `${st.prog}%` }} />
              </div>
              <span>{st.prog}%</span>
            </div>
            <div className="ltext">
              <div className="ln l" />
              <div className="ln m" />
              <div className="ln l hot" />
              <div className="ln s hot" />
              <div className="ln m" />
              <div className="ln l" />
            </div>
            <div className={`hintcard${st.showHint ? " show" : ""}`}>
              <div className="ht">
                <Bulb /> A simpler way to see it
              </div>
              <p>
                Think of the handshake like a phone call: you say hello, they say
                hello back, then you confirm you heard them. Three steps — that&apos;s it.
              </p>
            </div>
          </div>
          <div className="panel">
            <div className="ph">
              <span className="lbl">Live focus</span>
              <span className="live">
                <span className="bd" /> ON
              </span>
            </div>
            <div className="cam">
              <div className="eq">
                {Array.from({ length: 9 }).map((_, i) => (
                  <i key={i} />
                ))}
              </div>
              <span className="tag">behavioral + facial · on-device</span>
            </div>
            <div className="state-now">
              <div className="nm">
                <span className="ring" style={{ background: st.bg }}>
                  <i style={{ background: st.color }} />
                </span>
                <div>
                  <strong style={{ color: nameColor }}>{st.name}</strong>
                  <span>{st.hint}</span>
                </div>
              </div>
              <div className="conf">
                {st.bars.map((v, i) => (
                  <div className="row" key={i}>
                    <span className="k">{st.keys[i]}</span>
                    <div className="bar">
                      <i style={{ width: `${v}%`, background: i === 0 ? st.color : "var(--brand)" }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="loop-note">
              <Refresh /> Re-checking every 30s
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Static showcase device (product preview)                            */
/* ------------------------------------------------------------------ */

function ShowcaseMock() {
  return (
    <div className="showcase reveal d2" aria-hidden="true">
      <div className="browser">
        <div className="browser-bar">
          <div className="traffic">
            <i />
            <i />
            <i />
          </div>
          <div className="url">
            <UrlLock /> app.affectlearn.com/lesson
          </div>
        </div>
        <div className="app">
          <div className="lesson">
            <div className="crumb">Foundations of Agentic AI · Lesson 1.1</div>
            <h3>Trace the agent loop</h3>
            <div className="lprog">
              <div className="ptrack">
                <i style={{ width: "84%" }} />
              </div>
              <span>84%</span>
            </div>
            <div className="ltext">
              <div className="ln l" />
              <div className="ln m" />
              <div className="ln s" />
              <div className="ln l" />
              <div className="ln m" />
            </div>
            <div
              className="hintcard show"
              style={{ borderColor: "#bfdbfe", background: "linear-gradient(180deg,#eff6ff,#fff)" }}
            >
              <div className="ht" style={{ color: "var(--brand-600)" }}>
                <Bolt /> Ready for a challenge?
              </div>
              <p>
                You&apos;re moving fast — want to skip ahead to the interactive
                subnet calculator instead of the recap?
              </p>
            </div>
          </div>
          <div className="panel">
            <div className="ph">
              <span className="lbl">Live focus</span>
              <span className="live">
                <span className="bd" /> ON
              </span>
            </div>
            <div className="cam">
              <div className="eq">
                {Array.from({ length: 9 }).map((_, i) => (
                  <i key={i} />
                ))}
              </div>
              <span className="tag">behavioral + facial · on-device</span>
            </div>
            <div className="state-now">
              <div className="nm">
                <span className="ring" style={{ background: "rgba(100,116,139,.16)" }}>
                  <i style={{ background: "var(--bored)" }} />
                </span>
                <div>
                  <strong>Bored</strong>
                  <span>This part feels familiar</span>
                </div>
              </div>
              <div className="conf">
                <div className="row">
                  <span className="k">Bored</span>
                  <div className="bar">
                    <i style={{ width: "71%", background: "var(--bored)" }} />
                  </div>
                </div>
                <div className="row">
                  <span className="k">Engaged</span>
                  <div className="bar">
                    <i style={{ width: "21%" }} />
                  </div>
                </div>
                <div className="row">
                  <span className="k">Confused</span>
                  <div className="bar">
                    <i style={{ width: "8%" }} />
                  </div>
                </div>
              </div>
            </div>
            <div className="loop-note">
              <Refresh /> Re-checking every 30s
            </div>
          </div>
        </div>
      </div>
      <div className="toast">
        <div className="ti">
          <Bolt />
        </div>
        <div>
          <strong>Skipping ahead</strong>
          <p>You&apos;ve got this — jumping to the challenge.</p>
        </div>
      </div>
      <div className="toast b">
        <div className="ti">
          <Alert />
        </div>
        <div>
          <strong>Take a 5-min break?</strong>
          <p>A reset can help this concept land.</p>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* FAQ                                                                  */
/* ------------------------------------------------------------------ */

const FAQS: Array<{ q: string; a: string }> = [
  {
    q: "Does AffectLearn record or store my webcam video?",
    a: "No. Frames are analyzed in real time, the moment they're captured, and immediately discarded. No video is ever written to disk, transmitted, or reviewed by a person. Only an anonymous read of your current state is used to adapt the lesson.",
  },
  {
    q: "What if I don't want to turn my camera on?",
    a: "That's completely fine. AffectLearn switches to behavioral-only mode and reads how you move through the lesson — reading pace, hesitation, navigation patterns — to keep adapting. You'll always see clearly which mode you're in.",
  },
  {
    q: "What states can it actually detect?",
    a: "Two, and we would rather say so than claim four. Confusion is read from how you work — mouse, scroll and typing rhythm — and drifting attention is read from the camera. Frustration and boredom have no detector we would trust, so the system does not pretend to see them. Confusion brings a hint; drifting attention nudges the lesson on.",
  },
  {
    q: "Will it interrupt me or take over my lesson?",
    a: "Never. Every adaptation is a suggestion you can accept or dismiss. Hints appear calmly beside your content rather than as blocking pop-ups, and you stay in control of your path through the material.",
  },
  {
    q: "What do I need to get started?",
    a: "Just a modern browser and, optionally, a standard webcam — nothing to install. After a quick 30-second calibration where you read a short paragraph, the platform establishes your baseline and you're ready to learn.",
  },
  {
    q: "I teach a course — how do I bring it onto AffectLearn?",
    a: "Structure your material as lessons, sections, exercises and quizzes, then upload it through the creator dashboard. As learners progress, you'll get per-section affect analytics showing exactly where they struggle — so you can improve with evidence.",
  },
];

function Faq() {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="faq">
      {FAQS.map((item, i) => {
        const isOpen = open === i;
        return (
          <div className={`qa reveal${isOpen ? " open" : ""}`} key={i}>
            <button aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : i)}>
              <span>{item.q}</span>
              <span className="ico">
                <Plus />
              </span>
            </button>
            <div className="ans" style={{ maxHeight: isOpen ? 400 : 0 }}>
              <p>{item.a}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                 */
/* ------------------------------------------------------------------ */

export default function LandingPage() {
  const { accessToken, expiresAt, user } = useSessionStore();
  const router = useRouter();
  const rootRef = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);

  const isAuthenticated =
    accessToken !== null && expiresAt !== null && Date.now() < expiresAt;

  useEffect(() => {
    if (isAuthenticated && user) {
      router.replace(ROLE_DASHBOARDS[user.role] ?? "/courses");
    }
  }, [isAuthenticated, user, router]);

  // nav shadow on scroll
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 14);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // scroll reveal
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const els = root.querySelectorAll<HTMLElement>(".reveal:not(.in)");
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  if (isAuthenticated && user) return null;

  return (
    <div className="al-landing" ref={rootRef}>
      {/* FAQ structured data for rich results (built from the FAQS above) */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            mainEntity: FAQS.map((f) => ({
              "@type": "Question",
              name: f.q,
              acceptedAnswer: { "@type": "Answer", text: f.a },
            })),
          }),
        }}
      />

      {/* ============ NAV ============ */}
      <header className={`nav${scrolled ? " scrolled" : ""}`}>
        <div className="wrap nav-inner">
          <Link className="brand" href="#top" aria-label="AffectLearn home">
            <span>
              Affect<b>Learn</b>
            </span>
          </Link>
          <nav className="nav-links">
            <a className="link" href="#how">How it works</a>
            <a className="link" href="#features">Features</a>
            <a className="link" href="#audiences">For educators</a>
            <a className="link" href="#privacy">Privacy</a>
            <a className="link" href="#faq">FAQ</a>
          </nav>
          <div className="nav-cta">
            <Link className="btn btn-quiet" href="/login">Sign in</Link>
            <Link className="btn btn-primary" href="/register">
              Start learning
              <ArrowRight />
            </Link>
          </div>
        </div>
      </header>

      <span id="top" />

      {/* ============ HERO ============ */}
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <h1 className="display hero-title reveal in d1">
              Learning that adapts to <em>how you feel</em>, not just what you score.
            </h1>
            <p className="hero-sub reveal in d2">
              AffectLearn senses the moment you get stuck or start drifting, then
              reshapes the lesson in real time. A hint when you&apos;re lost, a nudge
              onward when you&apos;ve stalled, a breather when you need one. All from a
              standard webcam and your browser.
            </p>
            <div className="hero-actions reveal in d3">
              <Link className="btn btn-primary btn-lg" href="/register">
                Start learning free
                <ArrowRight />
              </Link>
              <a className="btn btn-ghost btn-lg" href="#how">
                <PlayCircle />
                See how it works
              </a>
            </div>
            <div className="hero-trust reveal in d4">
              <span className="t">
                <Shield /> No image ever leaves your device
              </span>
              <span className="t">
                <Lock /> Private by design
              </span>
              <span className="t">
                <Activity /> Works in any modern browser
              </span>
            </div>
          </div>

          <HeroMock />
        </div>
      </section>

      {/* ============ LOGOS STRIP ============ */}
      <div className="strip">
        <div className="wrap">
          <p className="lab">
            Built for self-paced learners and the educators who design their courses
          </p>
        </div>
      </div>

      {/* ============ HOW IT WORKS ============ */}
      <section className="block" id="how">
        <div className="wrap">
          <div className="sec-head reveal">
            <span className="eyebrow">How it works</span>
            <h2 className="display">A continuous loop that listens, understands, and responds.</h2>
            <p>
              Every 30 seconds, AffectLearn reads subtle signals — facial expression
              and how you move through the page — to understand your state and gently
              adjust what you see next.
            </p>
          </div>
          <div className="loop">
            <div className="step reveal d1">
              <div className="no">01</div>
              <div className="ic"><Eye /></div>
              <h4>Sense</h4>
              <p>Reads facial micro-expressions and your reading rhythm — scroll pace, dwell time, hesitation.</p>
              <div className="arrow"><ArrowRight /></div>
            </div>
            <div className="step reveal d2">
              <div className="no">02</div>
              <div className="ic"><ClockSimple /></div>
              <h4>Understand</h4>
              <p>Each signal answers the question it is good at — your camera reads drifting attention, your typing and scrolling read confusion.</p>
              <div className="arrow"><ArrowRight /></div>
            </div>
            <div className="step reveal d3">
              <div className="no">03</div>
              <div className="ic"><Bulb /></div>
              <h4>Decide</h4>
              <p>Weighs your state against your progress and pace to choose the most helpful next move.</p>
              <div className="arrow"><ArrowRight /></div>
            </div>
            <div className="step reveal d4">
              <div className="no">04</div>
              <div className="ic"><Trend /></div>
              <h4>Adapt</h4>
              <p>Offers a hint, a different explanation, a move onward, or a well-timed break — always as a suggestion you can wave away.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ============ FEATURES ============ */}
      <section className="block" id="features" style={{ paddingTop: 0 }}>
        <div className="wrap">
          <div className="sec-head reveal">
            <span className="eyebrow">What it does</span>
            <h2 className="display">Support that arrives exactly when you need it.</h2>
            <p>Not before, not after. AffectLearn responds to your real state in the moment so momentum never breaks.</p>
          </div>
          <div className="features">
            <div className="feat reveal d1">
              <div className="ic"><Bulb /></div>
              <h4>Hints when you&apos;re stuck</h4>
              <p>Re-reading the same paragraph? A focused hint or simpler analogy slides in to unblock you, then steps aside.</p>
            </div>
            <div className="feat reveal d2">
              <div className="ic"><Bolt /></div>
              <h4>Challenge when you&apos;re ahead</h4>
              <p>Breezing through familiar material? The lesson skips the obvious and offers a harder, more rewarding problem.</p>
            </div>
            <div className="feat reveal d3">
              <div className="ic"><Alert /></div>
              <h4>A break before burnout</h4>
              <p>When frustration builds, AffectLearn suggests a short reset, and returns with a fresh way to explain the idea.</p>
            </div>
            <div className="feat reveal d1">
              <div className="ic"><Layout /></div>
              <h4>Formats that switch for you</h4>
              <p>If dense text isn&apos;t landing, the same concept reappears as a visual walkthrough or a hands-on exercise.</p>
            </div>
            <div className="feat reveal d2">
              <div className="ic"><Check /></div>
              <h4>You&apos;re always in control</h4>
              <p>Every adaptation is a suggestion you can accept or dismiss. AffectLearn guides, it never takes the wheel.</p>
            </div>
            <div className="feat reveal d3">
              <div className="ic"><Shield /></div>
              <h4>Works without a webcam</h4>
              <p>Prefer camera off? The platform reads your interaction patterns instead and keeps adapting, with full transparency.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ============ PRODUCT PREVIEW ============ */}
      <section className="block preview">
        <div className="wrap preview-grid">
          <div>
            <div className="sec-head left reveal" style={{ marginBottom: 34 }}>
              <span className="eyebrow">In the lesson</span>
              <h2 className="display">See adaptation happen, live.</h2>
            </div>
            <div className="annot">
              <div className="item reveal d1">
                <div className="n">1</div>
                <div>
                  <h4>A focus panel you can trust</h4>
                  <p>A small, always-visible panel shows your current state and that detection is running on-device — never a black box.</p>
                </div>
              </div>
              <div className="item reveal d2">
                <div className="n">2</div>
                <div>
                  <h4>Hints that read the room</h4>
                  <p>When confusion lingers on a tough concept, a gentle hint appears beside the content — not a pop-up that interrupts.</p>
                </div>
              </div>
              <div className="item reveal d3">
                <div className="n">3</div>
                <div>
                  <h4>Pace that meets you</h4>
                  <p>Attention drifting for more than a moment nudges the lesson forward rather than leaving you stuck on a page you have stopped reading.</p>
                </div>
              </div>
            </div>
          </div>
          <ShowcaseMock />
        </div>
      </section>

      {/* ============ AUDIENCES ============ */}
      <section className="block" id="audiences">
        <div className="wrap">
          <div className="sec-head reveal">
            <span className="eyebrow">Two sides, one platform</span>
            <h2 className="display">Built for learners. Loved by educators.</h2>
          </div>
          <div className="audiences">
            <div className="aud learner reveal d1">
              <span className="tagb">For learners</span>
              <h3>Finish the modules you&apos;d normally abandon.</h3>
              <p className="lead">
                Study independently without feeling alone. AffectLearn notices when
                you&apos;re drifting and meets you with the right support — so you keep
                going and actually finish.
              </p>
              <ul>
                <li><CheckBold /> Help that arrives the moment you&apos;re stuck</li>
                <li><CheckBold /> Pace and difficulty tuned to you</li>
                <li><CheckBold /> Pick up right where you left off, every time</li>
              </ul>
              <Link className="btn btn-primary" href="/register">
                Start learning
                <ArrowRight />
              </Link>
            </div>
            <div className="aud creator reveal d2">
              <span className="tagb">For course creators</span>
              <h3>See exactly where students struggle.</h3>
              <p className="lead">
                Not just whether they passed — but which section lost them, and how.
                Turn real emotional signals into precise, confident course improvements.
              </p>
              <ul>
                <li><CheckBold /> Per-section affect heatmaps</li>
                <li><CheckBold /> Spot your top confusion &amp; boredom points</li>
                <li><CheckBold /> Redesign with evidence, not guesswork</li>
              </ul>
              <Link className="btn btn-primary alt" href="/login">
                Explore the creator tools
                <ArrowRight />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ============ PRIVACY ============ */}
      <section className="block privacy" id="privacy">
        <div className="wrap">
          <div className="privacy-grid">
            <div className="reveal">
              <span className="eyebrow">Privacy by design</span>
              <h2>No video. <em>Ever.</em></h2>
              <p className="lead">
                Reading your expressions doesn&apos;t mean recording your face. Frames
                are analyzed the instant they&apos;re captured and immediately discarded
                — nothing is saved, sent, or seen by a human.
              </p>
            </div>
            <div className="priv-list">
              <div className="priv-card reveal d1">
                <div className="ic"><EyeOff /></div>
                <h4>Nothing recorded</h4>
                <p>Webcam frames never touch disk or database. Processed in memory, then gone.</p>
              </div>
              <div className="priv-card reveal d2">
                <div className="ic"><Lock /></div>
                <h4>You hold the switch</h4>
                <p>Turn the camera off anytime. The platform keeps working in behavioral-only mode.</p>
              </div>
              <div className="priv-card reveal d3">
                <div className="ic"><UserPlus /></div>
                <h4>No identity attached</h4>
                <p>Your learning signals stay private — never sold, never linked to advertising profiles.</p>
              </div>
              <div className="priv-card reveal d4">
                <div className="ic"><ShieldPlain /></div>
                <h4>Encrypted end to end</h4>
                <p>Everything in transit and at rest is encrypted to modern standards. Clear consent, always.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ EVIDENCE ============ */}
      {/*
        This section replaced three fabricated testimonials — invented learners and an invented
        named academic. On a public page that is a straightforward misrepresentation, and it was
        also the weakest thing here: every competitor can invent a quote, and none of them can
        show a measured number with its sample and its limits.

        Every figure below is reported with the corpus it was measured on and the number of
        held-out participants behind it. The last card states plainly that no learner trial has
        run, because a page that lists two AUCs and stays silent about that would imply an
        outcome claim the work does not have.
      */}
      <section className="block" id="evidence">
        <div className="wrap">
          <div className="sec-head reveal">
            <span className="eyebrow">Evidence</span>
            <h2 className="display">Measured, not asserted.</h2>
            <p className="lead">
              Affect detection is easy to claim and hard to do. Here is what ours actually
              scores, on public benchmarks, with the sample behind each number.
            </p>
          </div>
          <div className="quotes">
            <div className="q reveal d1">
              <div className="eyebrow">Disengagement, from the camera</div>
              <div style={{ fontSize: 44, fontWeight: 600, letterSpacing: "-.02em", lineHeight: 1 }}>
                0.92<small style={{ fontSize: ".45em", fontWeight: 700, opacity: .75 }}> AUC</small>
              </div>
              <blockquote>
                Measured on EngageNet across 26 held-out participants — people the model had never
                seen. The best published result on the same benchmark is 0.74. The model reads
                facial <em>geometry</em>, not pixels: about 600 bytes leave your browser per
                cycle, against the ~3.3 MB a face crop would cost.
              </blockquote>
            </div>
            <div className="q reveal d2">
              <div className="eyebrow">Confusion, from how you work</div>
              <div style={{ fontSize: 44, fontWeight: 600, letterSpacing: "-.02em", lineHeight: 1 }}>
                0.74<small style={{ fontSize: ".45em", fontWeight: 700, opacity: .75 }}> AUC</small>
              </div>
              <blockquote>
                Measured on DUX across 46 annotated sessions, from mouse, scroll and typing
                rhythm alone. On the one dataset that carries both signals, interaction beat
                facial expression for confusion — which is the opposite of what most of the field
                assumes, so we publish it rather than bury it.
              </blockquote>
            </div>
            <div className="q reveal d3">
              <div className="eyebrow">What we have not measured</div>
              <div style={{ fontSize: 44, fontWeight: 600, letterSpacing: "-.02em", lineHeight: 1 }}>
                Not yet
              </div>
              <blockquote>
                Whether adaptation improves learning outcomes is an open question here. The
                trial that would answer it has not run, so we do not claim a result. Two of the
                four classic states — boredom and frustration — have no detector we would stand
                behind either, so the system acts on the two it can actually see.
              </blockquote>
            </div>
          </div>
        </div>
      </section>

      {/* ============ FAQ ============ */}
      <section className="block" id="faq" style={{ background: "#f8fafc", borderTop: "1px solid var(--line)" }}>
        <div className="wrap">
          <div className="sec-head reveal">
            <span className="eyebrow">Questions</span>
            <h2 className="display">Good to know.</h2>
          </div>
          <Faq />
        </div>
      </section>

      {/* ============ FOOTER ============ */}
      <footer className="ft" id="start">
        <div className="wrap">
          <div className="ft-grid">
            <div className="ft-brand">
              <Link className="brand" href="#top">
                <span>
                  Affect<b>Learn</b>
                </span>
              </Link>
              <p>Adaptive learning that responds to how you feel — so you keep going, and finish.</p>
            </div>
            <div className="ft-col">
              <h5>Product</h5>
              <a href="#how">How it works</a>
              <a href="#features">Features</a>
              <a href="#evidence">Evidence</a>
              <a href="#audiences">For creators</a>
            </div>
            <div className="ft-col">
              <h5>Company</h5>
              <a href="#evidence">About the research</a>
              <Link href="/login">Sign in</Link>
              <Link href="/register">Sign up</Link>
              <a href="#faq">FAQ</a>
            </div>
            {/*
              These four used to point at `#privacy` and `#faq` — on-page anchors, on a site whose
              central promise is privacy. A footer link labelled "Privacy policy" that scrolls you
              to a marketing section is worse than no link at all.
            */}
            <div className="ft-col">
              <h5>Legal</h5>
              <Link href="/legal/privacy">Privacy policy</Link>
              <Link href="/legal/terms">Terms of service</Link>
              <Link href="/legal/data-and-consent">Data &amp; consent</Link>
              <Link href="/legal/accessibility">Accessibility</Link>
            </div>
          </div>
          {/*
            The social row here held three icons — X, LinkedIn, GitHub — all pointing at `#top`.
            No such accounts exist, so they were decoration shaped like links. A footer with no
            social icons is unremarkable; one with three that go nowhere is a defect.
          */}
          <div className="ft-bottom">
            <p>© {new Date().getFullYear()} AffectLearn. All rights reserved.</p>
            <p>A research project. <Link href="/legal/data-and-consent">What that means</Link>.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
