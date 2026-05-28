export default function CoursesEditorPage() {
  const courses = [
    {
      id: "1",
      title: "Computer Networking Fundamentals",
      modules: 4,
      lessons: 18,
      enrollments: 36,
      status: "published",
    },
    {
      id: "2",
      title: "Introduction to Databases",
      modules: 3,
      lessons: 12,
      enrollments: 24,
      status: "published",
    },
    {
      id: "3",
      title: "Operating Systems Concepts",
      modules: 2,
      lessons: 8,
      enrollments: 0,
      status: "draft",
    },
  ];

  const STATUS_STYLES: Record<string, string> = {
    published: "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    draft: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  };

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Courses</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage and edit your course content
          </p>
        </div>
        <button
          className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          disabled
          title="Course creation coming soon"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Course
        </button>
      </div>

      <div className="space-y-3">
        {courses.map((course) => (
          <div
            key={course.id}
            className="flex items-center justify-between rounded-lg border border-border bg-surface px-5 py-4 transition-colors hover:bg-background/50"
          >
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-1">
                <h3 className="font-semibold text-foreground">{course.title}</h3>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[course.status]}`}
                >
                  {course.status}
                </span>
              </div>
              <p className="text-sm text-muted-foreground">
                {course.modules} modules · {course.lessons} lessons · {course.enrollments} enrolled learners
              </p>
            </div>
            <div className="flex items-center gap-2 ml-4">
              <button
                className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
                disabled
                title="Analytics view coming soon"
              >
                Analytics
              </button>
              <button
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                disabled
                title="Course editor coming soon"
              >
                Edit
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
