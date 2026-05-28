export default function AdminSettingsPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Admin Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Platform configuration and research study parameters
        </p>
      </div>

      <div className="space-y-6">
        <section className="rounded-lg border border-border bg-surface p-6">
          <h2 className="mb-1 font-semibold text-foreground">Affect Detection</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Configure the detection loop interval and confidence thresholds
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { label: "Detection interval (seconds)", value: "30" },
              { label: "Minimum confidence threshold", value: "0.65" },
              { label: "Consecutive cycles before intervention", value: "2" },
              { label: "Break suggestion threshold (frustration)", value: "0.80" },
            ].map((setting) => (
              <div key={setting.label}>
                <label className="block text-sm font-medium text-foreground mb-1">
                  {setting.label}
                </label>
                <input
                  type="text"
                  defaultValue={setting.value}
                  disabled
                  className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground opacity-70 cursor-not-allowed"
                />
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-border bg-surface p-6">
          <h2 className="mb-1 font-semibold text-foreground">Study Parameters</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Research study configuration for the pilot
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { label: "Self-report interval (sections)", value: "2" },
              { label: "Data retention period (days)", value: "90" },
              { label: "Session timeout (minutes)", value: "120" },
            ].map((setting) => (
              <div key={setting.label}>
                <label className="block text-sm font-medium text-foreground mb-1">
                  {setting.label}
                </label>
                <input
                  type="text"
                  defaultValue={setting.value}
                  disabled
                  className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground opacity-70 cursor-not-allowed"
                />
              </div>
            ))}
          </div>
        </section>

        <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800/40 dark:bg-amber-900/20 px-4 py-3">
          <svg className="h-4 w-4 text-amber-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p className="text-sm text-amber-700 dark:text-amber-400">
            Settings are read-only during an active pilot study session. Contact the system administrator to make changes.
          </p>
        </div>
      </div>
    </div>
  );
}
