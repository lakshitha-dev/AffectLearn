export interface SectionProgress {
  id: string;
  userId: string;
  sectionId: string;
  enrollmentId: string;
  completedAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface LessonProgressResponse {
  lessonId: string;
  totalSections: number;
  completedSectionIds: string[];
  lessonPercentage: number;
}

export interface CourseProgressResponse {
  completedSectionIds: string[];
  coursePercentage: number;
}

export interface ResumeTarget {
  courseId: string;
  moduleId: string;
  lessonId: string;
  sectionId: string;
  courseTitle: string;
  moduleTitle: string;
  lessonTitle: string;
  sectionTitle: string;
  isLessonComplete: boolean;
  isCourseComplete: boolean;
}
