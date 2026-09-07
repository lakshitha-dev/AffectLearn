import { apiFetch } from "@/lib/api-client";
import type { ContentBlock, SectionDetail } from "@/types/course";

/**
 * Write a block of `blockType` into `section`, creating it when it does not exist yet.
 *
 * The quiz and exercise tabs previously wrote only when a block of their type was ALREADY on the
 * section — `if (quizBlock) { PUT }` — but toasted success unconditionally. A designer authoring
 * the first quiz for a section therefore filled the form, pressed Save, was told "Quiz saved", and
 * lost the work on the next navigation. Nothing failed loudly because nothing was attempted.
 *
 * Creating the block is the missing half, and it belongs here rather than duplicated in each tab:
 * the two callers had already drifted (the exercise tab seeds its form from the existing block,
 * the quiz tab did not), and a silent-write bug is exactly the kind that reappears when the fix
 * lives in two places.
 */
export async function upsertBlock({
  section,
  blockType,
  content,
}: {
  section: SectionDetail | undefined;
  blockType: ContentBlock["blockType"];
  content: Record<string, unknown>;
}): Promise<ContentBlock> {
  if (!section) {
    // The lesson has no section to hang a block on. Surfaced to the caller as a failed save
    // rather than swallowed, so the designer is never told their work was stored when it was not.
    throw new Error("This lesson has no sections yet — add one before authoring blocks.");
  }

  const existing = section.contentBlocks?.find((b) => b.blockType === blockType);

  if (existing) {
    return apiFetch<ContentBlock>(`/courses/content-blocks/${existing.id}`, {
      method: "PUT",
      body: JSON.stringify({ content, blockType }),
    });
  }

  // Append after whatever the section already holds; `sortOrder` is required and must not collide.
  const sortOrder = section.contentBlocks?.length ?? 0;
  return apiFetch<ContentBlock>(`/courses/sections/${section.id}/content-blocks`, {
    method: "POST",
    body: JSON.stringify({ blockType, content, sortOrder }),
  });
}
