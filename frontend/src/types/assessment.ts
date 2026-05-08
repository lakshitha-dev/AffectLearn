export interface AssessmentOption {
  id: string;
  text: string;
  sortOrder: number;
}

export interface AssessmentQuestion {
  id: string;
  text: string;
  sortOrder: number;
  options: AssessmentOption[];
}

export interface Assessment {
  id: string;
  moduleId: string;
  assessmentType: "pre" | "post";
  title: string;
  questions: AssessmentQuestion[];
}

export interface AnswerPayload {
  questionId: string;
  selectedOptionId: string;
}

export interface QuestionResultOption extends AssessmentOption {
  isCorrect: boolean;
}

export interface QuestionResult {
  id: string;
  text: string;
  sortOrder: number;
  explanation: string | null;
  options: QuestionResultOption[];
  selectedOptionId: string | null;
  isCorrect: boolean;
}

export interface AttemptResult {
  id: string;
  score: number;
  maxScore: number;
  submittedAt: string;
  questions: QuestionResult[];
  preScore: number | null;
  preMaxScore: number | null;
}
