export interface ContentBlock {
  id: string;
  blockType: "text" | "code" | "image" | "callout" | "exercise" | "quiz" | "table";
  content: Record<string, unknown>;
  sortOrder: number;
  variantKey: string;
  variantGroup: string;
  sectionId: string;
  createdAt: string;
  updatedAt: string;
}

export interface Section {
  id: string;
  title: string;
  sortOrder: number;
  estimatedDurationMinutes: number | null;
  lessonId: string;
  contentBlocks?: ContentBlock[];
  createdAt: string;
  updatedAt: string;
}

export interface Lesson {
  id: string;
  title: string;
  description: string | null;
  sortOrder: number;
  moduleId: string;
  sections?: Section[];
  createdAt: string;
  updatedAt: string;
}

export interface Module {
  id: string;
  title: string;
  description: string | null;
  sortOrder: number;
  courseId: string;
  lessons?: Lesson[];
  createdAt: string;
  updatedAt: string;
}

export interface Course {
  id: string;
  title: string;
  description: string | null;
  estimatedDurationMinutes: number | null;
  isPublished: boolean;
  learningObjectives?: string | null;
  createdAt: string;
  updatedAt: string;
  // Optional annotations populated when caller is an authenticated learner.
  isEnrolled?: boolean | null;
  enrollmentProgress?: number | null;
  moduleCount?: number | null;
}

export interface CourseDetail extends Course {
  modules: Module[];
}

export interface CourseListResponse {
  items: Course[];
  total: number;
  page: number;
  pageSize: number;
}

export interface SectionDetail extends Section {
  contentBlocks: ContentBlock[];
}

export interface LessonDetail extends Lesson {
  sections: SectionDetail[];
}
