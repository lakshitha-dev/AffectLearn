export default function UsersPage() {
  const users = [
    { id: "1", name: "Alex Chen", email: "alex@university.edu", role: "learner", status: "Active", joined: "2026-04-10" },
    { id: "2", name: "Jordan Lee", email: "jordan@university.edu", role: "learner", status: "Active", joined: "2026-04-12" },
    { id: "3", name: "Sam Rivera", email: "sam@university.edu", role: "learner", status: "Inactive", joined: "2026-03-28" },
    { id: "4", name: "Dr. Morgan", email: "morgan@university.edu", role: "course_designer", status: "Active", joined: "2026-03-01" },
    { id: "5", name: "Prof. Taylor", email: "taylor@university.edu", role: "course_designer", status: "Active", joined: "2026-02-15" },
  ];

  const ROLE_BADGE: Record<string, string> = {
    learner: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    course_designer: "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    admin: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  };

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">User Management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage learner, designer, and admin accounts
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary">
            {users.length} users
          </span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { label: "Total Learners", value: users.filter(u => u.role === "learner").length, color: "text-blue-600" },
          { label: "Course Designers", value: users.filter(u => u.role === "course_designer").length, color: "text-purple-600" },
          { label: "Active This Week", value: users.filter(u => u.status === "Active").length, color: "text-green-600" },
        ].map((stat) => (
          <div key={stat.label} className="rounded-lg border border-border bg-surface p-4">
            <p className="text-sm text-muted-foreground">{stat.label}</p>
            <p className={`mt-1 text-2xl font-bold ${stat.color}`}>{stat.value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Email</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Role</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Joined</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user, i) => (
              <tr
                key={user.id}
                className={`border-b border-border last:border-0 ${i % 2 === 0 ? "" : "bg-background/50"}`}
              >
                <td className="px-4 py-3 font-medium text-foreground">{user.name}</td>
                <td className="px-4 py-3 text-muted-foreground">{user.email}</td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${ROLE_BADGE[user.role]}`}>
                    {user.role.replace("_", " ")}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${user.status === "Active" ? "text-green-600" : "text-muted-foreground"}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${user.status === "Active" ? "bg-green-500" : "bg-muted-foreground"}`} />
                    {user.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted-foreground">{user.joined}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
