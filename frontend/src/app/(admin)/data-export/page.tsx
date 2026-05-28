export default function DataExportPage() {
  const exports = [
    { label: "Learner Affect Time-Series", description: "Timestamped affect state classifications per learner session", format: "CSV", size: "~2.4 MB" },
    { label: "Quiz Response Data", description: "All quiz answers, timestamps, and correctness scores", format: "CSV", size: "~0.8 MB" },
    { label: "Behavioral Signals", description: "Mouse/keyboard event aggregates per 30-second window", format: "JSON", size: "~5.1 MB" },
    { label: "Pre/Post Assessment Results", description: "Knowledge scores from pre- and post-module assessments", format: "CSV", size: "~0.3 MB" },
    { label: "Full Study Dataset", description: "All data combined in a single anonymised export", format: "ZIP", size: "~8.9 MB" },
  ];

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Data Export</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Download research datasets for offline analysis
        </p>
      </div>

      <div className="mb-6 flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800/40 dark:bg-blue-900/10 px-5 py-4">
        <svg className="h-4 w-4 text-blue-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-sm text-blue-700 dark:text-blue-400">
          All exports are fully anonymised — no names, emails, or identifiable information included. Learner IDs are pseudonymised.
        </p>
      </div>

      <div className="space-y-3">
        {exports.map((item) => (
          <div
            key={item.label}
            className="flex items-center justify-between rounded-lg border border-border bg-surface px-5 py-4"
          >
            <div className="flex-1 mr-4">
              <p className="font-medium text-foreground">{item.label}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">{item.description}</p>
            </div>
            <div className="flex items-center gap-4 shrink-0">
              <div className="text-right hidden sm:block">
                <p className="text-xs font-medium text-muted-foreground">{item.format}</p>
                <p className="text-xs text-muted-foreground">{item.size}</p>
              </div>
              <button
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                disabled
                title="Connect to backend to enable exports"
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Export
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
