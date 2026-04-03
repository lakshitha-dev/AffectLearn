"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-24">
      <h2 className="text-2xl font-bold">Something went wrong!</h2>
      <p className="mt-2 text-muted">{error.message}</p>
      <button
        className="mt-4 rounded-md bg-primary px-4 py-2 text-white"
        onClick={() => reset()}
      >
        Try again
      </button>
    </div>
  );
}
