import Link from "next/link";

/**
 * Shell for the four legal pages the landing-page footer links to.
 *
 * Those links previously all resolved to `#privacy` — an on-page anchor — on a site whose central
 * promise is privacy. A footer that says "Privacy policy" and scrolls you to a marketing section
 * is worse than no link at all, so these are real pages.
 *
 * Deliberately plain: no `landing.css`, no reveal animations, no marketing chrome. A policy page
 * should read like a document, and mixing it with the sales page's styling invites the suspicion
 * that it is one.
 */
export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white text-slate-900">
      <header className="border-b border-slate-200">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-5">
          <Link href="/" className="text-[15px] font-semibold tracking-tight">
            AffectLearn
          </Link>
          <nav className="flex gap-5 text-[13.5px] text-slate-600">
            <Link className="hover:text-slate-900" href="/legal/privacy">Privacy</Link>
            <Link className="hover:text-slate-900" href="/legal/terms">Terms</Link>
            <Link className="hover:text-slate-900" href="/legal/data-and-consent">Data</Link>
            <Link className="hover:text-slate-900" href="/legal/accessibility">Accessibility</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-12">
        <article
          className="
            [&_h1]:mb-2 [&_h1]:text-[32px] [&_h1]:font-semibold [&_h1]:tracking-tight
            [&_h2]:mb-3 [&_h2]:mt-10 [&_h2]:text-[19px] [&_h2]:font-semibold
            [&_p]:mb-4 [&_p]:text-[15.5px] [&_p]:leading-[1.7] [&_p]:text-slate-700
            [&_ul]:mb-4 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-5
            [&_li]:text-[15.5px] [&_li]:leading-[1.7] [&_li]:text-slate-700
            [&_a]:font-medium [&_a]:text-blue-700 [&_a]:underline
            [&_strong]:font-semibold [&_strong]:text-slate-900
          "
        >
          {children}
        </article>
      </main>

      <footer className="border-t border-slate-200">
        <div className="mx-auto max-w-3xl px-6 py-8 text-[13px] text-slate-500">
          <Link className="hover:text-slate-900" href="/">← Back to AffectLearn</Link>
        </div>
      </footer>
    </div>
  );
}
