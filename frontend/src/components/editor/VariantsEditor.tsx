"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api-client";
import type { ContentBlock, SectionDetail } from "@/types/course";

interface VariantsEditorProps {
  section: SectionDetail | undefined;
  lessonId: string;
}

/** The alternatives the adaptation loop knows how to select. */
const VARIANTS = [
  {
    key: "simpler",
    label: "Simpler",
    when: "Shown when a learner is confused — the loop picks this for a breakdown or a plainer retelling.",
    placeholder: "The same idea in plainer words, or broken into steps…",
  },
  {
    key: "harder",
    label: "Harder",
    when: "Shown when a learner is bored — the loop raises the challenge instead of removing it.",
    placeholder: "A more demanding version of this material…",
  },
  {
    key: "alternative",
    label: "Different angle",
    when: "A second explanation of the same point, for when the first one has not landed.",
    placeholder: "The same point approached from somewhere else…",
  },
] as const;

/**
 * Author the alternative renderings the adaptation loop selects between (FR19 / FR21).
 *
 * `content_blocks` has carried `variant_key` and `variant_group` since the first content
 * migration, and nothing ever wrote anything but "original" into them. The consequence was
 * visible in the learner experience: `show_alternative` and `increase_difficulty` had nothing to
 * select, so they fell through to an LLM paraphrase of the section, and `skip_ahead` degraded to
 * "scroll to the next section". The platform's central claim — that content adapts to the
 * learner — had no authored content to adapt TO.
 *
 * A variant never appears in the ordinary reading order: learner-facing reads filter to the
 * original. Writing one only gives the loop something better than generated prose to reach for.
 */
export function VariantsEditor({ section, lessonId }: VariantsEditorProps) {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [seededFor, setSeededFor] = useState<string | undefined>(section?.id);

  const original = section?.contentBlocks?.find(
    (b) => b.blockType === "text" && (b.variantKey ?? "original") === "original"
  );

  const variantsQuery = useQuery<ContentBlock[]>({
    queryKey: ["blockVariants", original?.id],
    queryFn: () => apiFetch<ContentBlock[]>(`/courses/content-blocks/${original!.id}/variants`),
    enabled: Boolean(original?.id),
  });

  // Seed each box from what is stored, once per section, so reopening the editor shows the
  // authored variant rather than an empty field that would overwrite it on save.
  const stored: Record<string, string> = {};
  for (const block of variantsQuery.data ?? []) {
    const key = block.variantKey ?? "original";
    if (key !== "original") {
      stored[key] = ((block.content as { text?: string })?.text ?? "") as string;
    }
  }
  if (seededFor !== section?.id) {
    setSeededFor(section?.id);
    setDrafts({});
  }

  async function save(variantKey: string) {
    if (!original) return;
    const text = (drafts[variantKey] ?? stored[variantKey] ?? "").trim();
    if (!text) {
      toast.error("Write the variant before saving it");
      return;
    }
    setSaving(variantKey);
    try {
      await apiFetch(`/courses/content-blocks/${original.id}/variants`, {
        method: "POST",
        body: JSON.stringify({ variantKey, content: { text } }),
      });
      await queryClient.invalidateQueries({ queryKey: ["blockVariants", original.id] });
      await queryClient.invalidateQueries({ queryKey: ["lessonDetail", lessonId] });
      toast.success("Variant saved");
    } catch {
      toast.error("Could not save the variant");
    } finally {
      setSaving(null);
    }
  }

  if (!section) return null;

  return (
    <div className="space-y-5 border-t border-border pt-8">
      <div>
        <h2 className="font-semibold text-foreground">Adaptive variants</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Alternative versions of this section&apos;s text. Learners never see these in the normal
          reading order — the adaptation loop swaps one in when it detects confusion or boredom.
        </p>
      </div>

      {!original ? (
        <p className="rounded-lg border border-dashed border-border bg-surface p-5 text-sm text-muted-foreground">
          Write the section&apos;s content above first. A variant is an alternative to something,
          so there has to be an original for it to stand in for.
        </p>
      ) : (
        <div className="space-y-4">
          {VARIANTS.map((variant) => {
            const value = drafts[variant.key] ?? stored[variant.key] ?? "";
            const authored = Boolean(stored[variant.key]);
            return (
              <section
                key={variant.key}
                className="rounded-lg border border-border bg-surface p-5"
              >
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-foreground">{variant.label}</h3>
                  {authored && (
                    <span className="rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
                      Authored
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{variant.when}</p>
                <textarea
                  value={value}
                  onChange={(e) =>
                    setDrafts((prev) => ({ ...prev, [variant.key]: e.target.value }))
                  }
                  rows={4}
                  placeholder={variant.placeholder}
                  className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <div className="mt-3 flex justify-end">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={saving !== null || !value.trim()}
                    onClick={() => save(variant.key)}
                  >
                    {saving === variant.key ? "Saving…" : `Save ${variant.label.toLowerCase()}`}
                  </Button>
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
