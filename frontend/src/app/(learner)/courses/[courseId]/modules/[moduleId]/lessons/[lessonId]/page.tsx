"use client";

import { use, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Maximize2, Minimize2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList,
  BreadcrumbPage, BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { AffectDebugOverlay } from "@/components/learning/AffectDebugOverlay";
import { BehavioralDebugOverlay } from "@/components/learning/BehavioralDebugOverlay";
import { BreakSuggestion } from "@/components/learning/BreakSuggestion";
import { IncreaseDifficulty } from "@/components/learning/IncreaseDifficulty";
import { InlineAdaptations } from "@/components/learning/InlineAdaptations";
import { SkipAheadSuggestion, type SkipInteraction } from "@/components/learning/SkipAheadSuggestion";
import { LessonProgressBar } from "@/components/learning/LessonProgressBar";
import { SectionView } from "@/components/learning/SectionView";
import { useCourse, useEnrollmentStatus, useLessonDetail } from "@/hooks/use-courses";
import { useBehavioralSignals } from "@/hooks/use-behavioral-signals";
import { useMediaPipe } from "@/hooks/use-media-pipe";
import { useLessonProgress, useMarkSectionComplete } from "@/hooks/use-progress";
import { useWebSocket } from "@/hooks/use-websocket";
import { useUiStore } from "@/stores/ui-store";
import type { SectionDetail } from "@/types/course";

const AFFECT_DEBUG_ENABLED = process.env.NEXT_PUBLIC_AFFECT_DEBUG === "1";

interface PageProps {
  params: Promise<{ courseId: string; moduleId: string; lessonId: string }>;
}

export default function LessonPage({ params }: PageProps) {
  const { courseId, moduleId, lessonId } = use(params);
  const router = useRouter();
  const { focusMode, toggleFocusMode } = useUiStore();

  const courseQuery = useCourse(courseId);
  const enrollmentQuery = useEnrollmentStatus(courseId);
  const lessonQuery = useLessonDetail(lessonId);
  const progressQuery = useLessonProgress(lessonId);
  const markComplete = useMarkSectionComplete(courseId, lessonId);

  // Open the single learner WebSocket for affect detection + adaptation delivery.
  // Story 4.2+ hooks (facial features, behavioral window, adaptations) consume this connection
  // via the send function — do NOT open additional connections elsewhere.
  const { send } = useWebSocket();
  const { debug: affectDebug } = useMediaPipe({ send });
  // Behavioral signals run in ALL non-error modes (incl. webcam-denied), so this
  // is mounted unconditionally alongside the facial hook (Story 4.3). The debug
  // ref surfaces NFR9 data-loss metrics in the dev overlay (AC #10).
  const { debug: behavioralDebug } = useBehavioralSignals({ send });

  const completedSectionIds = new Set(progressQuery.data?.completedSectionIds ?? []);
  const lessonPercentage = progressQuery.data?.lessonPercentage ?? 0;

  useEffect(() => {
    if (!enrollmentQuery.isLoading && enrollmentQuery.isFetched && enrollmentQuery.data === null) {
      toast.info("You need to enroll in this course first.");
      router.replace(`/courses/${courseId}`);
    }
  }, [enrollmentQuery.isLoading, enrollmentQuery.isFetched, enrollmentQuery.data, courseId, router]);

  const hasScrolled = useRef(false);
  useEffect(() => {
    if (lessonQuery.data && !hasScrolled.current) {
      const hash = window.location.hash.slice(1);
      if (hash) {
        const el = document.getElementById(hash);
        if (el) { el.scrollIntoView({ behavior: "smooth" }); hasScrolled.current = true; }
      }
    }
  }, [lessonQuery.data]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "f" || e.key === "F" || (e.key === "Escape" && focusMode)) {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        toggleFocusMode();
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [focusMode, toggleFocusMode]);

  const handleMarkComplete = useCallback((sectionId: string) => {
    markComplete.mutate({ sectionId }, {
      onError: () => toast.error("Could not save your progress. Try again."),
      onSuccess: () => toast.success("Section complete"),
    });
  }, [markComplete]);

  const sections = (lessonQuery.data?.sections ?? []).slice().sort(
    (a, b) => a.sortOrder - b.sortOrder,
  ) as SectionDetail[];

  const handleSectionNav = (idx: number) => {
    if (idx < 0 || idx >= sections.length) return;
    const section = sections[idx];
    const el = document.getElementById("section-" + section.id);
    if (el) { el.scrollIntoView({ behavior: "smooth" }); history.replaceState(null, "", "#section-" + section.id); }
  };

  // Story 5.6: advance the content view to the NEXT section when the learner accepts a
  // skip_ahead suggestion. Reuses the SAME scroll-based mechanism as the prev/next buttons
  // (handleSectionNav → scrollIntoView + hash). Because the lesson page tracks no "current
  // section" cursor, we derive the in-view section from the URL hash (set by handleSectionNav
  // / the prev-next buttons) and advance to the one after it; falling back to the first
  // un-completed section, then to section 0→1. "harder section / challenge exercise" degrades
  // to "next section" until the content-variant catalog lands (Open Question #1, deferred from
  // 5.2 — we do NOT fabricate a challenge exercise). Graceful no-op when already at the last
  // section (handleSectionNav guards the out-of-range index).
  const handleSkipAhead = useCallback(() => {
    if (sections.length === 0) return;
    const hashId = window.location.hash.replace(/^#section-/, "");
    let baseIdx = sections.findIndex((s) => s.id === hashId);
    if (baseIdx < 0) {
      baseIdx = sections.findIndex((s) => !completedSectionIds.has(s.id));
    }
    if (baseIdx < 0) baseIdx = 0;
    handleSectionNav(baseIdx + 1);
  // handleSectionNav + the section/completed snapshots are recomputed each render; this
  // callback intentionally reads the latest values without re-subscribing.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sections, completedSectionIds]);

  // Story 5.6 (FR22): log an adaptation accept/dismiss upstream so the backend emits a
  // research event for the Learner Profiler (4.5) to refine future decisions. Rides the
  // EXISTING WS `send` channel — no second connection, no store mutation.
  const logAdaptationInteraction = useCallback(
    (adaptationId: string, action: "skip_ahead", interaction: SkipInteraction) => {
      send({
        type: "adaptation_interaction",
        ts: Date.now(),
        data: { adaptation_id: adaptationId, action, interaction },
      });
    },
    [send],
  );

  // Story 5.6 (FR22): stable callback for the increase_difficulty applied acknowledgement.
  // Wrapped in useCallback so IncreaseDifficulty's useEffect does not re-run on every
  // lesson-page re-render (the inline arrow would create a new reference each render,
  // causing the effect to fire unnecessarily — the appliedRef guard prevents double-logs
  // but the extra runs waste CPU in a real-time WS context).
  const logIncreaseDifficultyApplied = useCallback(
    (id: string) => {
      send({
        type: "adaptation_interaction",
        ts: Date.now(),
        data: { adaptation_id: id, action: "increase_difficulty", interaction: "applied" },
      });
    },
    [send],
  );

  const course = courseQuery.data;
  const currentModuleIdx = course?.modules.findIndex((m) => m.id === moduleId) ?? -1;
  const currentModule = course?.modules[currentModuleIdx];
  const currentLessonIdx = currentModule?.lessons?.findIndex((l) => l.id === lessonId) ?? -1;

  const hasNextLesson = (() => {
    if (!course || currentModuleIdx < 0) return false;
    const mod = course.modules[currentModuleIdx];
    if (!mod?.lessons) return false;
    if (currentLessonIdx < mod.lessons.length - 1) return true;
    return currentModuleIdx < course.modules.length - 1;
  })();

  const handleLastSectionCta = useCallback(() => {
    if (!course) return;
    const mod = course.modules[currentModuleIdx];
    if (!mod?.lessons) { router.push("/courses/" + courseId); return; }
    if (currentLessonIdx >= 0 && currentLessonIdx < mod.lessons.length - 1) {
      const nextLesson = mod.lessons[currentLessonIdx + 1];
      router.push("/courses/" + courseId + "/modules/" + moduleId + "/lessons/" + nextLesson.id);
    } else if (currentModuleIdx < course.modules.length - 1) {
      const nextMod = course.modules[currentModuleIdx + 1];
      const firstLesson = nextMod.lessons?.[0];
      if (firstLesson) router.push("/courses/" + courseId + "/modules/" + nextMod.id + "/lessons/" + firstLesson.id);
    } else {
      router.push("/courses/" + courseId);
    }
  }, [course, courseId, moduleId, currentModuleIdx, currentLessonIdx, router]);

  if (lessonQuery.isLoading || enrollmentQuery.isLoading) return <LessonSkeleton />;

  if (!lessonQuery.data) {
    return (
      <div className="p-8 space-y-4">
        <h1 className="text-2xl font-semibold">Lesson not found</h1>
        <Link href={"/courses/" + courseId}>
          <Button variant="outline">Back to course</Button>
        </Link>
      </div>
    );
  }

  const lesson = lessonQuery.data;

  return (
    <div className="max-w-3xl mx-auto px-8 pb-16">
      <LessonProgressBar value={lessonPercentage} />
      <header className="flex items-center justify-between py-4">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link href={"/courses/" + courseId}>{course?.title ?? "Course"}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>{currentModule?.title ?? "Module"}</BreadcrumbPage>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage aria-current="page">{lesson.title}</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <button onClick={toggleFocusMode} aria-pressed={focusMode} aria-label={focusMode ? "Exit focus mode" : "Enter focus mode"} className="rounded p-1.5 text-muted-foreground hover:bg-border transition-colors">
          {focusMode ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>
      </header>
      <h1 className="mt-2 mb-8 text-3xl font-semibold text-foreground">{lesson.title}</h1>
      {lesson.description && (
        <p className="mb-8 text-base text-muted-foreground">{lesson.description}</p>
      )}
      {sections.length === 0 ? (
        <p className="text-muted-foreground text-sm">This lesson has no content yet. Check back soon!</p>
      ) : (
        sections.map((section, idx) => (
          <SectionView
            key={section.id}
            section={section}
            isCompleted={completedSectionIds.has(section.id)}
            isLast={idx === sections.length - 1}
            hasPrev={idx > 0}
            lastSectionCta={hasNextLesson ? "Next lesson" : "Back to course"}
            onMarkComplete={handleMarkComplete}
            onNext={() => { if (idx === sections.length - 1) handleLastSectionCta(); else handleSectionNav(idx + 1); }}
            onPrev={() => handleSectionNav(idx - 1)}
            isSaving={markComplete.isPending}
          />
        ))
      )}
      {/* Inline adaptive hints (Story 5.4) — renders the latest show_* adaptation
          inline at a natural content break; non-inline actions are left in the
          queue for Stories 5.5–5.7. */}
      <InlineAdaptations />
      {/* Break suggestion overlay (Story 5.5) — renders the latest suggest_break
          adaptation as a fixed-position, semi-transparent overlay card (not a true
          modal; content stays visible, no scroll-lock). Non-suggest_break actions are
          left in the queue for 5.4/5.6/5.7. Its JSX position is not layout-sensitive
          since it is a fixed overlay. */}
      <BreakSuggestion />
      {/* Skip-ahead suggestion (Story 5.6) — renders the latest skip_ahead adaptation as an
          accept/dismiss inline suggestion. Accept advances to the next section via the same
          scroll-based nav as the prev/next buttons; accept/dismiss are logged upstream (FR22).
          Non-skip_ahead actions are left in the queue for 5.4/5.5/5.7. */}
      <SkipAheadSuggestion
        onSkip={handleSkipAhead}
        onInteraction={(id, interaction) => logAdaptationInteraction(id, "skip_ahead", interaction)}
      />
      {/* Difficulty increase (Story 5.6) — UI-LESS invisible swap (UX spec line 675). Renders
          nothing; the durable log is the server-side adaptation_delivered event. The optional
          client ack rides the same FR22 channel. The real harder-variant swap is deferred
          (content-variant catalog, Open Question #1). */}
      <IncreaseDifficulty onApplied={logIncreaseDifficultyApplied} />
      {AFFECT_DEBUG_ENABLED && <AffectDebugOverlay debugRef={affectDebug} />}
      {AFFECT_DEBUG_ENABLED && <BehavioralDebugOverlay debugRef={behavioralDebug} />}
    </div>
  );
}

function LessonSkeleton() {
  return (
    <div className="max-w-3xl mx-auto px-8 pb-16 animate-pulse">
      <div className="h-1 w-full bg-border mb-4" />
      <div className="flex justify-between py-4">
        <div className="h-4 w-64 bg-border rounded" />
        <div className="h-6 w-6 bg-border rounded" />
      </div>
      <div className="h-8 w-2/3 bg-border rounded mb-8 mt-2" />
      <div className="space-y-4">
        {[1, 2, 3].map((i) => <div key={i} className="h-24 bg-border rounded" />)}
      </div>
    </div>
  );
}