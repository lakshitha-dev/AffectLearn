"use client";

import { use, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ChevronDown, ChevronRight, Loader2, Plus } from "lucide-react";

import { useCourse } from "@/hooks/use-courses";
import {
  nextSortOrder,
  swapOrder,
  useCreateLesson,
  useCreateModule,
  useCreateSection,
  useDeleteLesson,
  useDeleteModule,
  useDeleteSection,
  useUpdateLesson,
  useUpdateModule,
  useUpdateSection,
} from "@/hooks/use-authoring";
import { SectionBlocks } from "@/components/editor/SectionBlocks";
import type { Lesson, Module, Section } from "@/types/course";

/**
 * The course structure builder: modules, lessons and sections.
 *
 * There was no way to create any of these from the UI. The lesson editor could change an
 * existing lesson's text, quiz and exercise, but the tree those lessons hang from could only be
 * built by seeding the database.
 *
 * Reordering goes through `swapOrder` rather than writing both positions directly, because
 * `sort_order` is unique per parent — see that function for why a naive swap fails.
 *
 * Everything is gated on the course's `canEdit`. A designer viewing someone else's course, or
 * anyone but an admin viewing seeded content, gets the same tree read-only rather than a set of
 * buttons that return 403.
 */
export default function CourseStructurePage({
  params,
}: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = use(params);
  const { data: course, isLoading, isError } = useCourse(courseId);

  const [openModules, setOpenModules] = useState<Set<string>>(new Set());
  const [openLessons, setOpenLessons] = useState<Set<string>>(new Set());

  const createModule = useCreateModule();
  const [addingModule, setAddingModule] = useState(false);
  const [moduleTitle, setModuleTitle] = useState("");

  if (isLoading) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading course…
      </p>
    );
  }
  if (isError || !course) {
    return <p className="text-sm text-muted-foreground">Could not load this course.</p>;
  }

  const editable = course.canEdit === true;
  const modules = [...(course.modules ?? [])].sort((a, b) => a.sortOrder - b.sortOrder);

  function toggle(set: Set<string>, id: string, apply: (s: Set<string>) => void) {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    apply(next);
  }

  return (
    <div>
      <Link
        href="/courses-editor"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> All courses
      </Link>

      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">{course.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {editable
            ? "Add modules, lessons and sections. Open a lesson to write its content."
            : "You can view this structure but not change it — it is seeded content, or another designer's course."}
        </p>
      </div>

      {modules.length === 0 && (
        <div className="mb-4 rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm font-medium text-foreground">No modules yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            A course is made of modules, which hold lessons, which hold sections.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {modules.map((module, index) => (
          <ModuleCard
            key={module.id}
            module={module}
            siblings={modules}
            index={index}
            editable={editable}
            courseId={courseId}
            isOpen={openModules.has(module.id)}
            onToggle={() => toggle(openModules, module.id, setOpenModules)}
            openLessons={openLessons}
            onToggleLesson={(id) => toggle(openLessons, id, setOpenLessons)}
          />
        ))}
      </div>

      {editable && (
        <div className="mt-4">
          {addingModule ? (
            <InlineCreate
              label="Module title"
              value={moduleTitle}
              onChange={setModuleTitle}
              pending={createModule.isPending}
              onCancel={() => {
                setAddingModule(false);
                setModuleTitle("");
              }}
              onSubmit={async () => {
                await createModule.mutateAsync({
                  courseId,
                  title: moduleTitle.trim(),
                  sortOrder: nextSortOrder(modules),
                });
                setModuleTitle("");
                setAddingModule(false);
              }}
            />
          ) : (
            <button
              type="button"
              onClick={() => setAddingModule(true)}
              className="flex items-center gap-2 rounded-md border border-dashed border-border px-4 py-2.5 text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              <Plus className="h-4 w-4" /> Add module
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

function ModuleCard({
  module,
  siblings,
  index,
  editable,
  courseId,
  isOpen,
  onToggle,
  openLessons,
  onToggleLesson,
}: {
  module: Module;
  siblings: Module[];
  index: number;
  editable: boolean;
  courseId: string;
  isOpen: boolean;
  onToggle: () => void;
  openLessons: Set<string>;
  onToggleLesson: (id: string) => void;
}) {
  const updateModule = useUpdateModule();
  const deleteModule = useDeleteModule();
  const createLesson = useCreateLesson();
  const [adding, setAdding] = useState(false);
  const [lessonTitle, setLessonTitle] = useState("");

  const lessons = [...(module.lessons ?? [])].sort((a, b) => a.sortOrder - b.sortOrder);

  return (
    <div className="rounded-lg border border-border bg-surface">
      <div className="flex items-center gap-2 px-4 py-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isOpen}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {isOpen ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate font-medium text-foreground">{module.title}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {lessons.length} lesson{lessons.length === 1 ? "" : "s"}
          </span>
        </button>

        {editable && (
          <RowActions
            index={index}
            total={siblings.length}
            onMove={(dir) =>
              swapOrder(siblings, module, siblings[index + dir], (id, sortOrder) =>
                updateModule.mutateAsync({ moduleId: id, patch: { sortOrder } }),
              )
            }
            onRename={(title) => updateModule.mutateAsync({ moduleId: module.id, patch: { title } })}
            onDelete={() => deleteModule.mutateAsync(module.id)}
            currentTitle={module.title}
            deleteWarning="Deleting a module removes its lessons, sections and content."
          />
        )}
      </div>

      {isOpen && (
        <div className="border-t border-border px-4 py-3 pl-10">
          {lessons.length === 0 && (
            <p className="mb-2 text-sm text-muted-foreground">No lessons in this module yet.</p>
          )}
          <div className="space-y-2">
            {lessons.map((lesson, lessonIndex) => (
              <LessonCard
                key={lesson.id}
                lesson={lesson}
                siblings={lessons}
                index={lessonIndex}
                editable={editable}
                courseId={courseId}
                moduleId={module.id}
                isOpen={openLessons.has(lesson.id)}
                onToggle={() => onToggleLesson(lesson.id)}
              />
            ))}
          </div>

          {editable && (
            <div className="mt-3">
              {adding ? (
                <InlineCreate
                  label="Lesson title"
                  value={lessonTitle}
                  onChange={setLessonTitle}
                  pending={createLesson.isPending}
                  onCancel={() => {
                    setAdding(false);
                    setLessonTitle("");
                  }}
                  onSubmit={async () => {
                    await createLesson.mutateAsync({
                      moduleId: module.id,
                      title: lessonTitle.trim(),
                      sortOrder: nextSortOrder(lessons),
                    });
                    setLessonTitle("");
                    setAdding(false);
                  }}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setAdding(true)}
                  className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
                >
                  <Plus className="h-3.5 w-3.5" /> Add lesson
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function LessonCard({
  lesson,
  siblings,
  index,
  editable,
  courseId,
  moduleId,
  isOpen,
  onToggle,
}: {
  lesson: Lesson;
  siblings: Lesson[];
  index: number;
  editable: boolean;
  courseId: string;
  moduleId: string;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const updateLesson = useUpdateLesson();
  const deleteLesson = useDeleteLesson();
  const createSection = useCreateSection();
  const [adding, setAdding] = useState(false);
  const [sectionTitle, setSectionTitle] = useState("");

  const sections = [...(lesson.sections ?? [])].sort((a, b) => a.sortOrder - b.sortOrder);

  return (
    <div className="rounded-md border border-border">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isOpen}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate text-sm text-foreground">{lesson.title}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {sections.length} section{sections.length === 1 ? "" : "s"}
          </span>
        </button>

        {/* The one screen that already worked. Writing a lesson's content is a different job
            from arranging the tree, so it stays its own page rather than being inlined here. */}
        <Link
          href={`/editor/${courseId}/${moduleId}/${lesson.id}`}
          className="shrink-0 rounded border border-border px-2 py-1 text-xs font-medium text-foreground"
        >
          {editable ? "Write content" : "View content"}
        </Link>

        {editable && (
          <RowActions
            index={index}
            total={siblings.length}
            onMove={(dir) =>
              swapOrder(siblings, lesson, siblings[index + dir], (id, sortOrder) =>
                updateLesson.mutateAsync({ lessonId: id, patch: { sortOrder } }),
              )
            }
            onRename={(title) => updateLesson.mutateAsync({ lessonId: lesson.id, patch: { title } })}
            onDelete={() => deleteLesson.mutateAsync(lesson.id)}
            currentTitle={lesson.title}
            deleteWarning="Deleting a lesson removes its sections and content."
          />
        )}
      </div>

      {isOpen && (
        <div className="border-t border-border px-3 py-2 pl-8">
          {sections.length === 0 && (
            <p className="mb-2 text-xs text-muted-foreground">No sections yet.</p>
          )}
          <ul className="space-y-1">
            {sections.map((section, sectionIndex) => (
              <SectionRow
                key={section.id}
                section={section}
                siblings={sections}
                index={sectionIndex}
                editable={editable}
              />
            ))}
          </ul>

          {editable && (
            <div className="mt-2">
              {adding ? (
                <InlineCreate
                  label="Section title"
                  value={sectionTitle}
                  onChange={setSectionTitle}
                  pending={createSection.isPending}
                  onCancel={() => {
                    setAdding(false);
                    setSectionTitle("");
                  }}
                  onSubmit={async () => {
                    await createSection.mutateAsync({
                      lessonId: lesson.id,
                      title: sectionTitle.trim(),
                      sortOrder: nextSortOrder(sections),
                    });
                    setSectionTitle("");
                    setAdding(false);
                  }}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setAdding(true)}
                  className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  <Plus className="h-3 w-3" /> Add section
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SectionRow({
  section,
  siblings,
  index,
  editable,
}: {
  section: Section;
  siblings: Section[];
  index: number;
  editable: boolean;
}) {
  const updateSection = useUpdateSection();
  const deleteSection = useDeleteSection();
  const [open, setOpen] = useState(false);

  const blockCount = section.contentBlocks?.length ?? 0;

  return (
    <li className="rounded border border-border">
      <div className="flex items-center gap-2 px-2.5 py-1.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
        >
          {open ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          )}
          <span className="min-w-0 flex-1 truncate text-xs text-foreground">{section.title}</span>
          <span
            className={`shrink-0 text-[11px] ${
              blockCount === 0 ? "text-amber-700 dark:text-amber-500" : "text-muted-foreground"
            }`}
          >
            {/* An empty section is worth flagging: the structure builder can create one, and
                until it has a block a learner opening it sees a blank page. */}
            {blockCount === 0 ? "empty" : `${blockCount} block${blockCount === 1 ? "" : "s"}`}
          </span>
        </button>
        {editable && (
          <RowActions
            index={index}
            total={siblings.length}
            onMove={(dir) =>
              swapOrder(siblings, section, siblings[index + dir], (id, sortOrder) =>
                updateSection.mutateAsync({ sectionId: id, patch: { sortOrder } }),
              )
            }
            onRename={(title) =>
              updateSection.mutateAsync({ sectionId: section.id, patch: { title } })
            }
            onDelete={() => deleteSection.mutateAsync(section.id)}
            currentTitle={section.title}
            deleteWarning="Deleting a section removes its content blocks."
          />
        )}
      </div>

      {open && (
        <div className="border-t border-border p-2.5">
          <SectionBlocks section={section} editable={editable} />
        </div>
      )}
    </li>
  );
}

/* ------------------------------------------------------------------ */

/**
 * Move / rename / delete for one row of the tree.
 *
 * Deletion asks for confirmation inline and names what else goes with it. Every level of this
 * tree cascades, so deleting a module silently takes its lessons, sections, blocks and the
 * learner progress attached to them — a plain "Are you sure?" would not convey that.
 */
function RowActions({
  index,
  total,
  onMove,
  onRename,
  onDelete,
  currentTitle,
  deleteWarning,
}: {
  index: number;
  total: number;
  onMove: (direction: -1 | 1) => Promise<void>;
  onRename: (title: string) => Promise<unknown>;
  onDelete: () => Promise<unknown>;
  currentTitle: string;
  deleteWarning: string;
}) {
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState(currentTitle);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }

  if (renaming) {
    return (
      <span className="flex shrink-0 items-center gap-1">
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-48 rounded border border-border bg-background px-2 py-1 text-xs"
        />
        <button
          type="button"
          disabled={!title.trim() || busy}
          onClick={async () => {
            await run(() => onRename(title.trim()));
            setRenaming(false);
          }}
          className="rounded border border-border px-2 py-1 text-xs font-medium disabled:opacity-50"
        >
          Save
        </button>
        <button
          type="button"
          onClick={() => {
            setTitle(currentTitle);
            setRenaming(false);
          }}
          className="rounded px-2 py-1 text-xs text-muted-foreground"
        >
          Cancel
        </button>
      </span>
    );
  }

  if (confirming) {
    return (
      <span className="flex shrink-0 items-center gap-2">
        <span className="text-xs text-red-700 dark:text-red-400">{deleteWarning}</span>
        <button
          type="button"
          disabled={busy}
          onClick={() => run(onDelete)}
          className="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          {busy ? "Deleting…" : "Delete"}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="rounded px-2 py-1 text-xs text-muted-foreground"
        >
          Cancel
        </button>
      </span>
    );
  }

  return (
    <span className="flex shrink-0 items-center gap-1">
      <button
        type="button"
        aria-label="Move up"
        disabled={index === 0 || busy}
        onClick={() => run(() => onMove(-1))}
        className="rounded px-1.5 py-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-30"
      >
        ↑
      </button>
      <button
        type="button"
        aria-label="Move down"
        disabled={index === total - 1 || busy}
        onClick={() => run(() => onMove(1))}
        className="rounded px-1.5 py-1 text-xs text-muted-foreground hover:text-foreground disabled:opacity-30"
      >
        ↓
      </button>
      <button
        type="button"
        onClick={() => setRenaming(true)}
        className="rounded px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
      >
        Rename
      </button>
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="rounded px-2 py-1 text-xs text-red-700 hover:underline dark:text-red-400"
      >
        Delete
      </button>
    </span>
  );
}

function InlineCreate({
  label,
  value,
  onChange,
  onSubmit,
  onCancel,
  pending,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => Promise<void>;
  onCancel: () => void;
  pending: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        autoFocus
        value={value}
        placeholder={label}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) void onSubmit();
          if (e.key === "Escape") onCancel();
        }}
        className="w-64 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
      />
      <button
        type="button"
        disabled={!value.trim() || pending}
        onClick={() => void onSubmit()}
        className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
      >
        {pending ? "Adding…" : "Add"}
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="rounded-md px-2 py-1.5 text-sm text-muted-foreground"
      >
        Cancel
      </button>
    </div>
  );
}
