export default function DesignerSettingsPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your designer profile and notification preferences
        </p>
      </div>

      <div className="space-y-6">
        <section className="rounded-lg border border-border bg-surface p-6">
          <h2 className="mb-4 font-semibold text-foreground">Profile</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { label: "First name", value: "Dr. Morgan" },
              { label: "Last name", value: "" },
              { label: "Email", value: "morgan@university.edu" },
              { label: "Department", value: "Computer Science" },
            ].map((field) => (
              <div key={field.label}>
                <label className="block text-sm font-medium text-foreground mb-1">
                  {field.label}
                </label>
                <input
                  type="text"
                  defaultValue={field.value}
                  disabled
                  className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground opacity-70 cursor-not-allowed"
                />
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-border bg-surface p-6">
          <h2 className="mb-1 font-semibold text-foreground">Analytics Notifications</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Choose when to receive email alerts about affect analytics
          </p>
          <div className="space-y-3">
            {[
              { label: "New confusion hotspot detected (> 40%)", defaultOn: true },
              { label: "Weekly analytics summary", defaultOn: true },
              { label: "Learner completes a module", defaultOn: false },
            ].map((pref) => (
              <div key={pref.label} className="flex items-center justify-between py-1">
                <span className="text-sm text-foreground">{pref.label}</span>
                <div
                  className={`h-5 w-9 rounded-full ${pref.defaultOn ? "bg-primary" : "bg-border"} cursor-not-allowed opacity-70`}
                />
              </div>
            ))}
          </div>
        </section>

        <div className="flex justify-end">
          <button
            disabled
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground opacity-50 cursor-not-allowed"
          >
            Save changes
          </button>
        </div>
      </div>
    </div>
  );
}
