"use client";

import { useEffect } from "react";

/**
 * Top-level error boundary.
 *
 * This used to render `error.message` straight onto the page. In a Next.js production build the
 * message of a server-side error is replaced with a generic string, but errors thrown in client
 * components are not redacted — so the boundary would print whatever the throw site happened to
 * say, which is a stack-adjacent detail written for a developer, in front of a learner mid-lesson.
 *
 * The `digest` is what actually helps: it is the id the server logs the real error under, so a
 * participant can quote it and someone can find the failure. That is the useful half of what was
 * being shown, and it is the half that reveals nothing.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // The detail still exists — in the console and in the server log — for whoever is debugging.
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-8 text-center">
      <h2 className="text-2xl font-bold text-foreground">Something went wrong</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        The page didn&apos;t load. Trying again usually works; if it doesn&apos;t, your progress
        is saved and you can come back to it.
      </p>

      {error.digest && (
        <p className="mt-4 font-mono text-xs text-muted-foreground">
          Reference: {error.digest}
        </p>
      )}

      <button
        className="mt-6 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        onClick={() => reset()}
      >
        Try again
      </button>
    </div>
  );
}
