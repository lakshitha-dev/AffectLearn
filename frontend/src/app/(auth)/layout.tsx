"use client";

import Link from "next/link";
import { GuestGuard } from "@/components/shared/guest-guard";

const iconProps = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2.2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const TRUST = [
  {
    title: "No video is ever stored",
    body: "Webcam frames are read in memory and discarded — never written to disk.",
    icon: (
      <svg viewBox="0 0 24 24" {...iconProps}>
        <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
  },
  {
    title: "Adapts in real time",
    body: "A hint when you're stuck, a challenge when you're ahead — every 30 seconds.",
    icon: (
      <svg viewBox="0 0 24 24" {...iconProps}>
        <path d="M4 17l6-6 4 4 6-7" />
        <path d="M20 8v4h-4" />
      </svg>
    ),
  },
  {
    title: "Works without a webcam",
    body: "Prefer camera off? The behavioral model keeps adapting from interaction signals.",
    icon: (
      <svg viewBox="0 0 24 24" {...iconProps}>
        <rect x="3" y="11" width="18" height="10" rx="2" />
        <path d="M7 11V8a5 5 0 0110 0v3" />
      </svg>
    ),
  },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <GuestGuard>
      <div className="grid min-h-screen lg:grid-cols-2">
        {/* ===== Brand panel (desktop) ===== */}
        <aside className="relative hidden overflow-hidden bg-secondary px-12 py-14 text-white lg:flex lg:flex-col lg:justify-between">
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(620px 360px at 12% 6%, rgba(37,99,235,.45), transparent 60%), radial-gradient(560px 320px at 92% 96%, rgba(37,99,235,.28), transparent 60%)",
            }}
          />
          <Link href="/" className="relative z-10 text-xl font-bold tracking-tight">
            Affect<span className="text-[#60a5fa]">Learn</span>
          </Link>

          <div className="relative z-10 max-w-md">
            <h2 className="text-3xl font-semibold leading-tight tracking-tight">
              Learning that adapts to how you feel.
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-slate-300">
              Sign in to pick up where you left off, or create an account and let
              the lesson meet you exactly where you are.
            </p>

            <ul className="mt-10 space-y-6">
              {TRUST.map((t) => (
                <li key={t.title} className="flex gap-4">
                  <span className="grid h-10 w-10 flex-none place-items-center bg-white/10 text-[#6ee7b7]">
                    {t.icon}
                  </span>
                  <div>
                    <p className="font-semibold">{t.title}</p>
                    <p className="mt-0.5 text-sm text-slate-400">{t.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <p className="relative z-10 text-xs text-slate-500">
            © {new Date().getFullYear()} AffectLearn. Private by design.
          </p>
        </aside>

        {/* ===== Form panel ===== */}
        <main className="flex min-h-screen flex-col bg-background px-4 py-8 sm:px-6">
          <div className="flex items-center justify-between">
            <Link href="/" className="text-lg font-bold tracking-tight text-foreground lg:hidden">
              Affect<span className="text-primary">Learn</span>
            </Link>
            <Link
              href="/"
              className="ml-auto inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              <span aria-hidden>←</span> Back to home
            </Link>
          </div>

          <div className="flex flex-1 items-center justify-center py-10">
            <div className="w-full max-w-md">{children}</div>
          </div>
        </main>
      </div>
    </GuestGuard>
  );
}
