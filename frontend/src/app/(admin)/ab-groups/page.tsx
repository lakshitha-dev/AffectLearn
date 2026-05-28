export default function ABGroupsPage() {
  const groups = [
    { id: "1", name: "Control Group", description: "Standard e-learning without affect detection", members: 12, condition: "control" },
    { id: "2", name: "Webcam Affect", description: "Full affect detection with webcam + behavioral signals", members: 11, condition: "webcam" },
    { id: "3", name: "Behavioral Only", description: "Affect detection via mouse/keyboard signals only", members: 13, condition: "behavioral" },
  ];

  const CONDITION_COLORS: Record<string, string> = {
    control: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    webcam: "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    behavioral: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">A/B Research Groups</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage experimental conditions for the pilot study
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3 mb-8">
        {groups.map((group) => (
          <div key={group.id} className="rounded-lg border border-border bg-surface p-5">
            <div className="flex items-start justify-between mb-3">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${CONDITION_COLORS[group.condition]}`}
              >
                {group.condition}
              </span>
              <span className="text-2xl font-bold text-foreground">{group.members}</span>
            </div>
            <h3 className="font-semibold text-foreground mb-1">{group.name}</h3>
            <p className="text-sm text-muted-foreground">{group.description}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-surface p-6">
        <h2 className="font-semibold text-foreground mb-2">Group Assignment</h2>
        <p className="text-sm text-muted-foreground">
          Learners are automatically assigned to groups during registration based on a balanced
          randomization algorithm. Manual reassignment can be done through the user management
          interface.
        </p>
        <div className="mt-4 flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800/40 dark:bg-amber-900/20 px-4 py-3">
          <svg className="h-4 w-4 text-amber-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <p className="text-sm text-amber-700 dark:text-amber-400">
            Reassigning participants during an active study session may affect result validity.
          </p>
        </div>
      </div>
    </div>
  );
}
