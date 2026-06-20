/**
 * Typed configuration for the post-study satisfaction survey (Story 6.4).
 *
 * The form is rendered data-driven from this config so the component and its tests stay
 * maintainable; the `value` strings are the wire contract with the backend schema
 * (`app/schemas/survey.py`) and MUST match its known set (`LIKERT_5` = "1".."5", keys Q1..Q4).
 *
 * No post-study survey instrument doc exists, so the items are DERIVED from the four AC
 * dimensions + the UX-spec anchor "The platform helped me when I needed it" (Open Question #1).
 * The >= 4.0/5 target is a research metric only — it is NOT enforced in the form.
 */

export type SurveyQuestionType = "likert";

export interface SurveyOption {
  value: string;
  label: string;
}

export interface SurveyQuestion {
  id: string;
  type: SurveyQuestionType;
  /** Human-readable dimension this item measures (for grouping / research traceability). */
  dimension: string;
  prompt: string;
  required: boolean;
  options: SurveyOption[];
}

const LIKERT_AGREE: SurveyOption[] = [
  { value: "1", label: "Strongly Disagree" },
  { value: "2", label: "Disagree" },
  { value: "3", label: "Neutral" },
  { value: "4", label: "Agree" },
  { value: "5", label: "Strongly Agree" },
];

export const SATISFACTION_QUESTIONS: SurveyQuestion[] = [
  {
    id: "Q1",
    type: "likert",
    dimension: "Perceived adaptation quality",
    // UX-spec anchor (>= 4.0/5 success target — research metric, not a gate).
    prompt: "The platform helped me when I needed it.",
    required: true,
    options: LIKERT_AGREE,
  },
  {
    id: "Q2",
    type: "likert",
    dimension: "Learning experience",
    prompt: "Overall, this was a good learning experience.",
    required: true,
    options: LIKERT_AGREE,
  },
  {
    id: "Q3",
    type: "likert",
    dimension: "Willingness to continue",
    prompt: "I would like to keep using AffectLearn for future learning.",
    required: true,
    options: LIKERT_AGREE,
  },
  {
    id: "Q4",
    type: "likert",
    dimension: "Overall satisfaction",
    prompt: "I am satisfied with AffectLearn overall.",
    required: true,
    options: LIKERT_AGREE,
  },
];

export const TOTAL_SURVEY_QUESTIONS = SATISFACTION_QUESTIONS.length;
