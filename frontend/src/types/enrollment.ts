export type EnrollmentStatus = "active" | "completed" | "dropped";

export interface Enrollment {
  id: string;
  userId: string;
  courseId: string;
  enrolledAt: string;
  progressPercentage: number;
  lastAccessedAt: string | null;
  status: EnrollmentStatus;
  createdAt: string;
  updatedAt: string;
}

export interface EnrollmentDetail extends Enrollment {
  courseTitle: string;
  courseDescription: string | null;
  courseEstimatedDurationMinutes: number | null;
  courseModuleCount: number;
}

export interface EnrollmentListResponse {
  items: EnrollmentDetail[];
  total: number;
  page: number;
  pageSize: number;
}
