export default function ContentEditorPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Content Editor</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Edit lesson content, quizzes, and exercises
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface p-8 flex flex-col items-center justify-center text-center min-h-[400px]">
        <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10">
          <svg className="h-7 w-7 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
        </div>
        <h2 className="mb-2 text-lg font-semibold text-foreground">Select a lesson to edit</h2>
        <p className="mb-6 max-w-sm text-sm text-muted-foreground">
          Open a course from the Courses page, then select a lesson to open it in the content
          editor. You can edit text, quizzes, and exercises inline.
        </p>
        <a
          href="/courses-editor"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Go to Courses
        </a>
      </div>
    </div>
  );
}
