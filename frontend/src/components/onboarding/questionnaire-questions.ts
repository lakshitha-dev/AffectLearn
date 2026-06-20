/**
 * Typed configuration for the pre-study questionnaire (Story 6.3).
 *
 * Sourced verbatim from `_bmad-output/planning-artifacts/pre-study-questionnaire.md`
 * (Sections A–E, Q1–Q14). The form is rendered data-driven from this config so the
 * component and its tests stay maintainable; the `value` strings are the wire contract
 * with the backend schema (`app/schemas/questionnaire.py`) and MUST match its known sets.
 *
 * Section F (Q15 consent) is intentionally omitted — informed consent is already collected
 * and persisted by Epic 3's ConsentStep.
 */

export type QuestionType = "single" | "multi" | "likert" | "matrix";

export interface Option {
  value: string;
  label: string;
}

export interface BaseQuestion {
  id: string;
  type: QuestionType;
  prompt: string;
  /** Required questions gate the Next button; multi-select (Q9) is optional. */
  required: boolean;
}

export interface SingleQuestion extends BaseQuestion {
  type: "single" | "likert";
  options: Option[];
}

export interface MultiQuestion extends BaseQuestion {
  type: "multi";
  options: Option[];
}

export interface MatrixQuestion extends BaseQuestion {
  type: "matrix";
  rows: Option[];
  options: Option[];
}

export type Question = SingleQuestion | MultiQuestion | MatrixQuestion;

export interface Section {
  id: string;
  title: string;
  questions: Question[];
}

const LIKERT_AGREE: Option[] = [
  { value: "1", label: "Strongly Disagree" },
  { value: "2", label: "Disagree" },
  { value: "3", label: "Neutral" },
  { value: "4", label: "Agree" },
  { value: "5", label: "Strongly Agree" },
];

const LIKERT_FREQ: Option[] = [
  { value: "1", label: "Never" },
  { value: "2", label: "Rarely" },
  { value: "3", label: "Sometimes" },
  { value: "4", label: "Often" },
  { value: "5", label: "Very Often" },
];

export const QUESTIONNAIRE_SECTIONS: Section[] = [
  {
    id: "demographics",
    title: "About you",
    questions: [
      {
        id: "Q1",
        type: "single",
        required: true,
        prompt: "Age",
        options: [
          { value: "18-20", label: "18-20" },
          { value: "21-23", label: "21-23" },
          { value: "24-26", label: "24-26" },
          { value: "27+", label: "27 or above" },
        ],
      },
      {
        id: "Q2",
        type: "single",
        required: true,
        prompt: "Gender",
        options: [
          { value: "male", label: "Male" },
          { value: "female", label: "Female" },
          { value: "nonbinary", label: "Non-binary / Other" },
          { value: "prefer_not_to_say", label: "Prefer not to say" },
        ],
      },
    ],
  },
  {
    id: "background",
    title: "Your online learning background",
    questions: [
      {
        id: "Q3",
        type: "single",
        required: true,
        prompt:
          "How frequently do you use online learning platforms (e.g., Coursera, Udemy, LinkedIn Learning, institutional LMS)?",
        options: [
          { value: "daily", label: "Daily" },
          { value: "several_per_week", label: "Several times a week" },
          { value: "weekly", label: "Once a week" },
          { value: "few_per_month", label: "A few times a month" },
          { value: "rarely_never", label: "Rarely or Never" },
        ],
      },
      {
        id: "Q4",
        type: "single",
        required: true,
        prompt:
          "Approximately how many online courses have you started in the past 12 months?",
        options: [
          { value: "0", label: "0" },
          { value: "1-2", label: "1-2" },
          { value: "3-5", label: "3-5" },
          { value: "6-10", label: "6-10" },
          { value: "10+", label: "More than 10" },
        ],
      },
      {
        id: "Q5",
        type: "single",
        required: true,
        prompt: "Of those, how many have you fully completed?",
        options: [
          { value: "0", label: "0" },
          { value: "1-2", label: "1-2" },
          { value: "3-5", label: "3-5" },
          { value: "6-10", label: "6-10" },
          { value: "10+", label: "More than 10" },
        ],
      },
    ],
  },
  {
    id: "technology",
    title: "Technology & preferences",
    questions: [
      {
        id: "Q6",
        type: "likert",
        required: true,
        prompt:
          "How comfortable are you with your webcam being active during an online learning session?",
        options: [
          { value: "1", label: "Very Uncomfortable" },
          { value: "2", label: "Uncomfortable" },
          { value: "3", label: "Neutral" },
          { value: "4", label: "Comfortable" },
          { value: "5", label: "Very Comfortable" },
        ],
      },
      {
        id: "Q7",
        type: "single",
        required: true,
        prompt: "What is your most preferred content format for learning new material?",
        options: [
          { value: "video", label: "Video explanations" },
          { value: "text", label: "Text-based reading / articles" },
          { value: "interactive", label: "Interactive exercises / hands-on practice" },
          { value: "visual", label: "Visual diagrams / infographics" },
        ],
      },
    ],
  },
  {
    id: "affect",
    title: "Your experiences while learning",
    questions: [
      {
        id: "Q8",
        type: "matrix",
        required: true,
        prompt:
          "How frequently do you experience the following states during online learning sessions?",
        rows: [
          { value: "boredom", label: "Boredom (loss of interest, wanting to do something else)" },
          { value: "confusion", label: "Confusion (not understanding the material, feeling lost)" },
          { value: "frustration", label: "Frustration (feeling stuck, annoyed, or overwhelmed)" },
          { value: "engagement", label: "Engagement (focused, interested, absorbed in the content)" },
        ],
        options: LIKERT_FREQ,
      },
      {
        id: "Q9",
        type: "multi",
        required: false,
        prompt:
          "When you feel disengaged (bored, confused, or frustrated) during an online course, what do you typically do? (Select all that apply)",
        options: [
          { value: "push_through", label: "Push through and continue anyway" },
          { value: "take_break", label: "Take a break and return later" },
          { value: "skip_ahead", label: "Skip ahead or switch to a different section" },
          { value: "search_alternatives", label: "Search for alternative explanations elsewhere" },
          { value: "stop_session", label: "Stop the session entirely" },
          { value: "ask_help", label: "Ask someone for help" },
        ],
      },
      {
        id: "Q10",
        type: "single",
        required: true,
        prompt:
          "Have you ever abandoned or dropped an online course primarily due to negative emotional experiences (boredom, confusion, frustration)?",
        options: [
          { value: "yes_multiple", label: "Yes, multiple times" },
          { value: "yes_once_twice", label: "Yes, once or twice" },
          { value: "no_considered", label: "No, but I have considered it" },
          { value: "no_never", label: "No, never" },
        ],
      },
      {
        id: "Q11",
        type: "likert",
        required: true,
        prompt:
          'To what extent do you agree: "If the online course had adapted to my emotional state (e.g., simplified content when I was confused, changed pace when I was bored), I would have been more likely to complete it."',
        options: LIKERT_AGREE,
      },
    ],
  },
  {
    id: "self-efficacy",
    title: "Your confidence in online learning",
    questions: [
      {
        id: "Q12",
        type: "likert",
        required: true,
        prompt:
          "I am confident in my ability to learn new concepts through online platforms.",
        options: LIKERT_AGREE,
      },
      {
        id: "Q13",
        type: "likert",
        required: true,
        prompt:
          "I can stay focused during an online learning session for at least 30 minutes.",
        options: LIKERT_AGREE,
      },
      {
        id: "Q14",
        type: "likert",
        required: true,
        prompt:
          "I can complete an online course module without external motivation or deadlines.",
        options: LIKERT_AGREE,
      },
    ],
  },
];

export const TOTAL_SECTIONS = QUESTIONNAIRE_SECTIONS.length;
