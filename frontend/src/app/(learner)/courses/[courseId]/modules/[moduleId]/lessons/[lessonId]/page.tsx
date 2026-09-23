"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Maximize2, Minimize2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList,
  BreadcrumbPage, BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { AffectDebugOverlay } from "@/components/learning/AffectDebugOverlay";
import { BehavioralDebugOverlay } from "@/components/learning/BehavioralDebugOverlay";
import { BreakSuggestion } from "@/components/learning/BreakSuggestion";
import { AdaptationProbe } from "@/components/learning/AdaptationProbe";
import { AdaptationDevPanel } from "@/components/learning/AdaptationDevPanel";
import { activeInlineAdaptation, InlineAdaptations } from "@/components/learning/InlineAdaptations";
import { SkipAheadSuggestion, type SkipInteraction } from "@/components/learning/SkipAheadSuggestion";
import { SelfReportBar, type SelfReport } from "@/components/learning/SelfReportBar";
import { LessonProgressBar } from "@/components/learning/LessonProgressBar";
import { SectionView } from "@/components/learning/SectionView";
import { useCourse, useEnrollmentStatus, useLessonDetail } from "@/hooks/use-courses";
import { useBehavioralSignals } from "@/hooks/use-behavioral-signals";
import { useSectionSignals } from "@/hooks/use-section-signals";
import { usePerformanceWindow } from "@/hooks/use-performance-window";
import { useSectionVisits, type SectionEntrySource } from "@/hooks/use-section-visits";
import { useMediaPipe } from "@/hooks/use-media-pipe";
import { useLessonProgress, useMarkSectionComplete, useRecordQuizResponse } from "@/hooks/use-progress";
import { useWebSocket } from "@/hooks/use-websocket";
import {
  useSelfReportTrigger,
  SECTIONS_PER_PROMPT,
  SELF_REPORT_OMISSION_RATE,
} from "@/hooks/use-self-report-trigger";
import { useAdaptationStore } from "@/stores/adaptation-store";
import { useUiStore } from "@/stores/ui-store";
import type { SectionDetail } from "@/types/course";
import type { AdaptationAction, HelpRequestKind } from "@/types/ws-messages";

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
  const recordQuiz = useRecordQuizResponse();

  // Open the single learner WebSocket for affect detection + adaptation delivery.
  // Story 4.2+ hooks (facial features, behavioral window, adaptations) consume this connection
  // via the send function — do NOT open additional connections elsewhere.
  const { send } = useWebSocket();
  // NOTE: `useMediaPipe` / `useBehavioralSignals` are mounted further down, after `sections`
  // and `currentIndex` exist, because they now need the current section id to ground the
  // adaptation prompts. Their call order is unconditional and stable across renders, which is
  // all React requires.

  const completedSectionIds = new Set(progressQuery.data?.completedSectionIds ?? []);
  const lessonPercentage = progressQuery.data?.lessonPercentage ?? 0;

  useEffect(() => {
    if (!enrollmentQuery.isLoading && enrollmentQuery.isFetched && enrollmentQuery.data === null) {
      toast.info("You need to enroll in this course first.");
      router.replace(`/courses/${courseId}`);
    }
  }, [enrollmentQuery.isLoading, enrollmentQuery.isFetched, enrollmentQuery.data, courseId, router]);

  // One-section-per-page navigation: `currentIndex` is the section the learner is on.
  // Initialize to the first not-yet-completed section (resume) once lesson + progress load.
  const [currentIndex, setCurrentIndex] = useState(0);
  const didInitIndex = useRef(false);
  useEffect(() => {
    if (didInitIndex.current) return;
    if (!lessonQuery.data || progressQuery.isLoading) return;
    const secs = (lessonQuery.data.sections ?? [])
      .slice()
      .sort((a, b) => a.sortOrder - b.sortOrder);
    if (secs.length === 0) return;
    const done = new Set(progressQuery.data?.completedSectionIds ?? []);
    const firstIncomplete = secs.findIndex((s) => !done.has(s.id));
    setCurrentIndex(firstIncomplete < 0 ? 0 : firstIncomplete);
    didInitIndex.current = true;
  }, [lessonQuery.data, progressQuery.isLoading, progressQuery.data]);

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

  const sections = (lessonQuery.data?.sections ?? []).slice().sort(
    (a, b) => a.sortOrder - b.sortOrder,
  ) as SectionDetail[];

  // The section the learner is actually reading. Sent with every affect cycle so the backend
  // can build `content_context` and ground the hint in this material — without it the LLM only
  // ever saw `content_topic: unknown` and could only produce generic study advice.
  const currentSectionId = sections[currentIndex]?.id;

  const { debug: affectDebug } = useMediaPipe({ send, sectionId: currentSectionId });
  // Behavioral signals run in ALL non-error modes (incl. webcam-denied), so this
  // is mounted unconditionally alongside the facial hook (Story 4.3). The debug
  // ref surfaces NFR9 data-loss metrics in the dev overlay (AC #10).
  const { debug: behavioralDebug, cycleNumber } = useBehavioralSignals({
    send,
    sectionId: currentSectionId,
  });

  // Per-section interaction counters for confusion detection (dark-shipped: logged for future
  // model training, never shown to the learner and never fed to the live model).
  const sectionSignals = useSectionSignals();
  // Every VISIT to a section, not only its completion — a section revisited and never
  // completed otherwise leaves no trace at all.
  const sectionVisits = useSectionVisits(currentSectionId);
  // The third detection channel: the struggle counters, on the live path rather than only in the
  // completion request. A learner who gets stuck and gives up never completes the section, so the
  // counters describing the hardest case were the ones that never arrived.
  usePerformanceWindow({
    send,
    sectionId: currentSectionId,
    snapshot: sectionSignals.snapshot,
  });
  useEffect(() => {
    sectionSignals.enterSection(currentSectionId);
  }, [currentSectionId, sectionSignals]);

  // Declared AFTER `sectionSignals` deliberately: a useCallback dependency array is evaluated
  // during render, so referencing a `const` declared further down would throw a TDZ error.
  const handleMarkComplete = useCallback((sectionId: string) => {
    markComplete.mutate(
      { sectionId, interactionSignals: sectionSignals.snapshot(sectionId) },
      {
        onError: () => toast.error("Could not save your progress. Try again."),
        onSuccess: () => toast.success("Section complete"),
      },
    );
  }, [markComplete, sectionSignals]);

  const handleSectionNav = (idx: number, source?: SectionEntrySource) => {
    if (idx < 0 || idx >= sections.length) return;
    // Backwards navigation is the paginated equivalent of scrolling back to re-read — one of the
    // clearest confusion signals this UI produces, and previously not recorded at all.
    if (idx < currentIndex) sectionSignals.recordBackNav(currentSectionId);
    // Tell the visit log HOW the learner got there before the section changes. Arriving by
    // "back" is a learner returning to material they had left; arriving by "next" is the normal
    // path; arriving by "skip" is the system moving them after they accepted an adaptation. The
    // three mean different things and cannot be recovered from timestamps.
    sectionVisits.setEntrySource(source ?? (idx < currentIndex ? "back" : "next"));
    setCurrentIndex(idx);
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Story 5.6 (FR22): log an adaptation accept/dismiss upstream so the backend emits a
  // research event for the Learner Profiler (4.5) to refine future decisions. Rides the
  // EXISTING WS `send` channel — no second connection, no store mutation.
  const logAdaptationInteraction = useCallback(
    (adaptationId: string, action: "skip_ahead", interaction: SkipInteraction) => {
      send({
        type: "adaptation_interaction",
        ts: Date.now(),
        // Coordinates, which this event carried on NEITHER axis before. The backend has always
        // promoted both to indexed columns when present; the client simply never sent them, so
        // every response landed with cycle_number 0 and no section, and could not be joined to
        // the material it happened in or the cycle whose detection triggered it.
        data: {
          adaptation_id: adaptationId,
          action,
          interaction,
          section_id: currentSectionId,
          cycle_number: cycleNumber.current,
        },
      });
    },
    [send, currentSectionId],
  );

  // Hints were the only adaptation type that reported nothing at all: skip_ahead and
  // increase_difficulty both logged an interaction, while show_hint / show_alternative /
  // show_breakdown / show_encouragement had an empty dismissal handler. So the content the study
  // is actually about produced no learner-response signal. Same WS channel, same event.
  const logHintInteraction = useCallback(
    (payload: { adaptation_id: string; action: string; interaction: "dismissed" | "accepted" }) => {
      send({
        type: "adaptation_interaction",
        ts: Date.now(),
        data: { ...payload, section_id: currentSectionId, cycle_number: cycleNumber.current },
      });
    },
    [send, currentSectionId],
  );

  // "Still stuck" / "I'd rather move on" from the card on screen. The server runs the same agents
  // for the next rung of the ladder and delivers the result like any other adaptation.
  const requestHelp = useCallback(
    (payload: { request: HelpRequestKind; adaptation_id: string; action: AdaptationAction }) => {
      send({
        type: "help_request",
        ts: Date.now(),
        data: { ...payload, section_id: currentSectionId, cycle_number: cycleNumber.current },
      });
    },
    [send, currentSectionId],
  );

  // The learner's appraisal of a specific intervention — the only ground truth that can speak to
  // whether one helped. Everything else answers a different question: `self_report` fires on
  // section completion and references no delivery, dismissal is an action rather than a judgement,
  // and the detector's own later reading is the instrument being evaluated.
  const logAdaptationProbe = useCallback(
    (payload: {
      adaptation_id: string;
      action: string;
      response: "helped" | "did_not_help" | "unsure" | null;
      dismissed: boolean;
      shown_after_ms: number;
    }) => {
      send({
        type: "adaptation_probe",
        ts: Date.now(),
        data: { ...payload, section_id: currentSectionId, cycle_number: cycleNumber.current },
      });
    },
    [send, currentSectionId],
  );

  // Pre-pilot research control (#7): log a due prompt that was RANDOMLY OMITTED (never shown)
  // so analysis can estimate the prompt's own reactive effect. Reuses the self_report channel
  // with an `omitted` marker; affect is null and it is NOT a user skip.
  const logSelfReportOmitted = useCallback(
    (prompt_index: number) => {
      send({
        type: "self_report",
        ts: Date.now(),
        data: {
          affect: null,
          skipped: false,
          omitted: true,
          prompt_index,
          section_id: currentSectionId,
          cycle_number: cycleNumber.current,
        },
      });
    },
    [send, currentSectionId],
  );

  // Story 6.2: self-report pause-point trigger. Derived from distinct section completions
  // (the page tracks no "sections viewed" counter; a scroll-spy is deliberately avoided —
  // see use-self-report-trigger.ts). The widget shows once SECTIONS_PER_PROMPT completions
  // accrue since the last prompt, then resets after a report/skip (never re-prompts
  // immediately, never blocks scrolling/navigation). A random SELF_REPORT_OMISSION_RATE
  // fraction of due prompts are omitted (logged, not shown) for reactivity estimation (#7).
  const { showSelfReport, promptIndex, dismiss: dismissSelfReport } = useSelfReportTrigger(
    completedSectionIds.size,
    SECTIONS_PER_PROMPT,
    { omissionRate: SELF_REPORT_OMISSION_RATE, onOmit: logSelfReportOmitted },
  );

  // Story 6.2: log the learner's ground-truth self-report (or deliberate skip) upstream so
  // the backend emits a `self_report` research event for model validation. Mirrors
  // logAdaptationInteraction: rides the EXISTING WS `send` channel — no second connection,
  // no new hook, no store mutation. A deliberate skip is {affect:null, skipped:true};
  // a prompt the learner never reaches emits nothing (missing data, not a skip).
  const logSelfReport = useCallback(
    (report: SelfReport, prompt_index: number) => {
      send({
        type: "self_report",
        ts: Date.now(),
        data: {
          affect: report.affect,
          skipped: report.skipped,
          prompt_index,
          // section_features declares the self-report join key to be learner_id + section_id,
          // and this is the only place that key can be supplied.
          section_id: currentSectionId,
          cycle_number: cycleNumber.current,
        },
      });
    },
    [send, currentSectionId],
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

  // Story 5.6: move the learner on when they accept a `skip_ahead` adaptation.
  //
  // This now does EXACTLY what the Next button does, which it previously did not, in two ways
  // that both looked like a broken button:
  //
  //   1. On the last section it advanced `currentIndex` to itself and stopped — a documented
  //      "graceful no-op". The learner clicked Skip ahead, the card disappeared, and nothing
  //      moved. Next, on that same section, calls `handleLastSectionCta` and crosses into the
  //      following lesson or module. A suggestion the system raised on its own initiative is the
  //      worst place to have a control that silently does nothing.
  //
  //   2. It bypassed `handleSectionNav`, so `sectionVisits.setEntrySource` never ran and the
  //      visit log recorded the arrival with whatever source was left over from the previous
  //      navigation. Skips were therefore indistinguishable from the learner pressing Next —
  //      in the one dataset that exists to tell learner choices from system decisions.
  //
  // The harder-content case is handled upstream now: with an authored `harder` variant the
  // Content Adapter serves that instead, so this path is the fallback for when no variant has
  // been written, not the only behaviour.
  const handleSkipAhead = useCallback(() => {
    const idx = Math.min(currentIndex, sections.length - 1);
    if (idx >= sections.length - 1) {
      // Out of sections: cross the lesson boundary exactly as Next does.
      handleLastSectionCta();
      return;
    }
    handleSectionNav(idx + 1, "skip");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentIndex, sections.length, handleLastSectionCta]);

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
    <div className="max-w-3xl mx-auto px-4 sm:px-8 pb-16">
      {/* Full-width back bar — flush to the content-column edges. Carries the exit
          action (Back to course) and the focus-mode toggle; the breadcrumb sits below
          as pure location context so a long course title never tangles with the button. */}
      <div className="-mx-4 sm:-mx-8">
        <LessonProgressBar value={lessonPercentage} />
        <div className="flex items-center justify-between gap-3 border-b border-border bg-surface px-4 py-2.5 sm:px-8">
          <Link
            href={"/courses/" + courseId}
            aria-label="Back to course"
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium text-foreground transition-colors hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to course
          </Link>
          <button
            onClick={toggleFocusMode}
            aria-pressed={focusMode}
            aria-label={focusMode ? "Exit focus mode" : "Enter focus mode"}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
          >
            {focusMode ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </div>
      <Breadcrumb className="mt-4 min-w-0">
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
      <h1 className="mt-3 mb-8 text-3xl font-semibold text-foreground">{lesson.title}</h1>
      {lesson.description && (
        <p className="mb-8 text-base text-muted-foreground">{lesson.description}</p>
      )}
      {sections.length === 0 ? (
        <p className="text-muted-foreground text-sm">This lesson has no content yet. Check back soon!</p>
      ) : (() => {
        // One section per page (client-side pagination) — keeps the single WebSocket
        // session + affect hooks mounted at the lesson level while showing one section.
        const idx = Math.min(currentIndex, sections.length - 1);
        const section = sections[idx];
        return (
          <>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Section {idx + 1} of {sections.length}
            </p>
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
              onShowAnswer={(sectionId) => sectionSignals.recordShowAnswer(sectionId)}
              onQuizAnswered={(sectionId, blockId, selectedIds, isCorrect, responseTimeMs) => {
                sectionSignals.recordQuizAttempt(sectionId, isCorrect, responseTimeMs);
                recordQuiz.mutate({
                  contentBlockId: blockId,
                  selectedAnswers: selectedIds,
                  isCorrect,
                  responseTimeMs,
                  sectionId,
                  // The hint on screen when this answer was given, if any. Read from the store
                  // at submit time rather than tracked separately, and through the same selector
                  // the callout renders with, so the page cannot attribute an answer to a hint
                  // the learner was not actually looking at.
                  assistanceId:
                    activeInlineAdaptation(useAdaptationStore.getState().adaptationQueue)?.id,
                });
              }}
            />
          </>
        );
      })()}
      {/* Inline adaptive hints (Story 5.4) — renders the latest show_* adaptation
          inline at a natural content break; non-inline actions are left in the
          queue for Stories 5.5–5.7. */}
      <InlineAdaptations
        onInteraction={logHintInteraction}
        onRequest={requestHelp}
        sectionId={currentSectionId ?? undefined}
      />
      {/* Asked once, 30s after a content intervention is delivered — long enough that the answer
          is about the help rather than about being interrupted. Inline, never blocking. */}
      <AdaptationProbe onRespond={logAdaptationProbe} />
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
      {/* `increase_difficulty` is no longer mounted separately. It used to render nothing at all —
          the harder-content catalogue it selected against does not exist — while auto-firing an
          "applied" acknowledgement from a useEffect on delivery. That ack was not a learner
          response: nothing had been applied and the learner had done nothing, so it put rows in
          adaptation_interaction that looked like engagement and were not. The action is now
          generative text and renders through InlineAdaptations above, where a dismissal is a real
          learner action. */}
      {/* Self-report affect widget (Story 6.2) — the pilot's ground-truth label source.
          Shown ONLY at a natural pause point (every ~3 section completions, derived by
          useSelfReportTrigger). Selection/skip is logged upstream as a self_report research
          event; on report the trigger resets so it never re-prompts immediately. Renders
          nothing when not at a pause point (no empty bar, no layout shift). */}
      {showSelfReport && (
        <SelfReportBar
          key={promptIndex}
          onReport={(report) => {
            logSelfReport(report, promptIndex);
            dismissSelfReport();
          }}
        />
      )}
      {AFFECT_DEBUG_ENABLED && <AffectDebugOverlay debugRef={affectDebug} />}
      {AFFECT_DEBUG_ENABLED && <BehavioralDebugOverlay debugRef={behavioralDebug} />}
      {/* Trigger panel for the adaptation loop. Same flag as the two overlays above, so a
          production build drops all three together. Five of the eight action types cannot be
          reached by using the product at all; this is how anyone sees them. */}
      {AFFECT_DEBUG_ENABLED && <AdaptationDevPanel sectionId={currentSectionId} />}
    </div>
  );
}

function LessonSkeleton() {
  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-8 pb-16 animate-pulse">
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