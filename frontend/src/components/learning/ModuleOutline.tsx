"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, ClipboardCheck, FileText } from "lucide-react";

import type { Module } from "@/types/course";

interface ModuleOutlineProps {
  courseId: string;
  module: Module;
  index: number;
  enrolled: boolean;
}

/**
 * One expandable module on the course overview, listing its lessons as links.
 *
 * The course page used to render module titles and a lesson COUNT and nothing else — the rows
 * were inert, and no lesson was reachable from them. The only way into content was the
 * Enrol/Continue button, which resumes wherever the learner left off, so a learner who wanted to
 * revisit lesson 2 of module 1 had no route to it short of clicking Continue and paging backwards.
 *
 * Links appear only once enrolled. The lesson route requires enrollment (progress writes are
 * refused without it), so offering the link to a browsing visitor would be offering a door that
 * does not open — the same "buttons that lie" problem the designer course list avoids by gating
 * on `canEdit`.
 */
export function ModuleOutline({ courseId, module, index, enrolled }: ModuleOutlineProps) {
  // The first module starts open: on a single-module course an all-collapsed outline shows the
  // learner nothing at all, which is what the old inert list already did.
  const [open, setOpen] = useState(index === 0);

  const lessons = [...(module.lessons ?? [])].sort((a, b) => a.sortOrder - b.sortOrder);
  const base = `/courses/${courseId}/modules/${module.id}`;

  return (
    <li className="rounded-lg border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-baseline gap-3 p-4 text-left"
      >
        {open ? (
          <ChevronDown className="h-4 w-4 shrink-0 translate-y-0.5 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 translate-y-0.5 text-muted-foreground" />
        )}
        <span className="flex-1">
          <span className="text-base font-medium text-foreground">
            <span className="mr-2 text-muted-foreground">{index + 1}.</span>
            {module.title}
          </span>
          {module.description ? (
            <span className="mt-1 block text-sm text-muted-foreground">
              {module.description}
            </span>
          ) : null}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {lessons.length} {lessons.length === 1 ? "lesson" : "lessons"}
        </span>
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3">
          {lessons.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              This module has no lessons yet.
            </p>
          ) : (
            <ul className="space-y-1">
              {/*
                The pre-assessment. Its route existed with ZERO inbound links anywhere in the app
                — reachable only by typing the URL — so the "let's see where you're starting from"
                step was effectively unreleased.
              */}
              {enrolled && (
                <li>
                  <Link
                    href={`${base}/assessment?type=pre`}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                  >
                    <ClipboardCheck className="h-4 w-4 shrink-0" />
                    Pre-assessment
                  </Link>
                </li>
              )}

              {lessons.map((lesson) =>
                enrolled ? (
                  <li key={lesson.id}>
                    <Link
                      href={`${base}/lessons/${lesson.id}`}
                      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-foreground transition-colors hover:bg-background"
                    >
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      {lesson.title}
                    </Link>
                  </li>
                ) : (
                  <li
                    key={lesson.id}
                    className="flex items-center gap-2 px-2 py-1.5 text-sm text-muted-foreground"
                  >
                    <FileText className="h-4 w-4 shrink-0" />
                    {lesson.title}
                  </li>
                )
              )}

              {enrolled && (
                <li>
                  <Link
                    href={`${base}/assessment?type=post`}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
                  >
                    <ClipboardCheck className="h-4 w-4 shrink-0" />
                    Post-assessment
                  </Link>
                </li>
              )}
            </ul>
          )}

          {!enrolled && lessons.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              Enrol to open these lessons.
            </p>
          )}
        </div>
      )}
    </li>
  );
}
