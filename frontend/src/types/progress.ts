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

// --- Learner progress aggregate (Story 4.6 → reused by Story 6.4 achievements summary) ---

export interface CourseProgressEntry {
  courseId: string;
  courseTitle: string;
  totalSections: number;
  completedSections: number;
  percentage: number;
}

export interface SectionProgressEntry {
  sectionId: string;
  completedAt: string;
  timeSpentSeconds?: number | null;
  affectStates?: string[] | null;
}

export interface QuizTally {
  answered: number;
  correct: number;
}

export interface LearnerProgressResponse {
  courses: CourseProgressEntry[];
  sections: SectionProgressEntry[];
  quizzes: QuizTally;
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
