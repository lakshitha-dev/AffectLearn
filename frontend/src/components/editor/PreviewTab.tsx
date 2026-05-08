import { ContentBlockRenderer } from "@/components/learning/ContentBlockRenderer";
import type { LessonDetail, SectionDetail } from "@/types/course";

interface PreviewTabProps {
  lesson: LessonDetail;
}

export function PreviewTab({ lesson }: PreviewTabProps) {
  const sections = (lesson.sections ?? []).slice().sort((a, b) => a.sortOrder - b.sortOrder) as SectionDetail[];

  if (sections.length === 0) {
    return <p className="text-muted-foreground text-sm">No sections to preview.</p>;
  }

  return (
    <div className="max-w-3xl space-y-10">
      {sections.map((section) => (
        <div key={section.id} className="space-y-5">
          <h2 className="text-2xl font-semibold text-foreground">{section.title}</h2>
          {section.contentBlocks
            .slice()
            .sort((a, b) => a.sortOrder - b.sortOrder)
            .map((block) => (
              <ContentBlockRenderer key={block.id} block={block} previewMode />
            ))}
        </div>
      ))}
    </div>
  );
}
