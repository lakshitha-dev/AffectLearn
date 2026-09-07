import Link from "next/link";

/**
 * 404.
 *
 * There was no `not-found.tsx`, so an unknown URL fell through to the framework's unstyled
 * default — a bare "404 | This page could not be found" on a white page, outside the app's chrome
 * and theme. Several links in the product pointed at routes that do not exist (a breadcrumb to a
 * non-existent editor path, a settings link into the onboarding wizard), so this was not a page
 * only a typo could reach.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8 text-center">
      <p className="font-mono text-sm text-muted-foreground">404</p>
      <h1 className="mt-2 text-2xl font-bold text-foreground">Page not found</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        That link doesn&apos;t lead anywhere. It may have been moved, or the address may be
        slightly off.
      </p>

      <div className="mt-6 flex gap-3">
        <Link
          href="/courses"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Go to my courses
        </Link>
        <Link
          href="/"
          className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-surface"
        >
          Home
        </Link>
      </div>
    </div>
  );
}
