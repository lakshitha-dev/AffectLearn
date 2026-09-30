/**
 * The pilot's questionnaires, as the participant reads them. The contract -- item ids, allowed
 * values, versions -- is mirrored in `backend/app/services/instruments.py`, which refuses anything
 * else; change both together and bump the version.
 *
 * SUS and UEQ-S are validated instruments and are reproduced VERBATIM: rewording an item, even to
 * name the product, changes what the published benchmarks can be compared against.
 *   - SUS: Brooke, J. (1996). SUS: a "quick and dirty" usability scale.
 *   - UEQ-S: Schrepp, M., Hinderks, A. & Thomaschewski, J. (2017). Design and evaluation of a
 *     short version of the User Experience Questionnaire (UEQ-S). IJIMAI 4(6), 103-108.
 * Lesson feedback is study-specific and NOT validated; its items are reported one by one.
 */

export type InstrumentName = "lesson_feedback" | "sus" | "ueq_s";

export interface ScaleOption {
  value: string;
  label: string;
}

export type InstrumentItem =
  | {
      id: string;
      kind: "scale";
      prompt: string;
      options: ScaleOption[];
      required: boolean;
      /** Show only when another item has one of these values. */
      showIf?: { item: string; values: string[] };
    }
  | {
      id: string;
      kind: "differential";
      /** Negative pole on the left, positive on the right (UEQ-S ordering). */
      left: string;
      right: string;
      required: boolean;
    };

export interface InstrumentDef {
  name: InstrumentName;
  version: string;
  title: string;
  intro: string;
  items: InstrumentItem[];
}

const AGREE_5: ScaleOption[] = [
  { value: "1", label: "Strongly disagree" },
  { value: "2", label: "Disagree" },
  { value: "3", label: "Neutral" },
  { value: "4", label: "Agree" },
  { value: "5", label: "Strongly agree" },
];

const DIFFICULTY_5: ScaleOption[] = [
  { value: "1", label: "Very easy" },
  { value: "2", label: "Easy" },
  { value: "3", label: "Moderate" },
  { value: "4", label: "Difficult" },
  { value: "5", label: "Very difficult" },
];

const NOTICED: ScaleOption[] = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "not_sure", label: "Not sure" },
];

const IF_NOTICED = { item: "noticed_change", values: ["yes"] };

export const LESSON_FEEDBACK: InstrumentDef = {
  name: "lesson_feedback",
  version: "1.0",
  title: "Quick feedback on this lesson",
  intro: "Four short questions about the lesson you just finished. There are no right answers.",
  items: [
    { id: "difficulty", kind: "scale", prompt: "How difficult was this lesson?",
      options: DIFFICULTY_5, required: true },
    { id: "easy_to_understand", kind: "scale", prompt: "The content was easy to understand.",
      options: AGREE_5, required: true },
    { id: "noticed_change", kind: "scale",
      prompt: "Did you notice the lesson changing or responding to you while you worked?",
      options: NOTICED, required: true },
    { id: "change_helpful", kind: "scale", prompt: "The changes were helpful.",
      options: AGREE_5, required: false, showIf: IF_NOTICED },
    { id: "change_distracting", kind: "scale", prompt: "The changes were distracting.",
      options: AGREE_5, required: false, showIf: IF_NOTICED },
    { id: "responded_to_needs", kind: "scale", prompt: "The system responded to what I needed.",
      options: AGREE_5, required: true },
  ],
};

const SUS_ITEMS = [
  "I think that I would like to use this system frequently.",
  "I found the system unnecessarily complex.",
  "I thought the system was easy to use.",
  "I think that I would need the support of a technical person to be able to use this system.",
  "I found the various functions in this system were well integrated.",
  "I thought there was too much inconsistency in this system.",
  "I would imagine that most people would learn to use this system very quickly.",
  "I found the system very cumbersome to use.",
  "I felt very confident using the system.",
  "I needed to learn a lot of things before I could get going with this system.",
];

export const SUS: InstrumentDef = {
  name: "sus",
  version: "1.0",
  title: "Using the system",
  intro:
    "For each statement, choose how much you agree. “The system” means AffectLearn as you just used it.",
  items: SUS_ITEMS.map((prompt, i) => ({
    id: `q${i + 1}`, kind: "scale" as const, prompt, options: AGREE_5, required: true,
  })),
};

const UEQ_S_PAIRS: [string, string][] = [
  ["obstructive", "supportive"],
  ["complicated", "easy"],
  ["inefficient", "efficient"],
  ["confusing", "clear"],
  ["boring", "exciting"],
  ["not interesting", "interesting"],
  ["conventional", "inventive"],
  ["usual", "leading edge"],
];

export const UEQ_S: InstrumentDef = {
  name: "ueq_s",
  version: "1.0",
  title: "Your impression of the system",
  intro:
    "For each pair, pick the point that best matches your impression of AffectLearn. Answer spontaneously; there are no right or wrong answers.",
  items: UEQ_S_PAIRS.map(([left, right], i) => ({
    id: `q${i + 1}`, kind: "differential" as const, left, right, required: true,
  })),
};

export const DIFFERENTIAL_POINTS = ["1", "2", "3", "4", "5", "6", "7"];

/** Whether an item is currently shown, given the answers so far. */
export function isVisible(item: InstrumentItem, values: Record<string, string>): boolean {
  if (item.kind !== "scale" || !item.showIf) return true;
  return item.showIf.values.includes(values[item.showIf.item] ?? "");
}

/** Whether every shown, required item has an answer. */
export function isComplete(def: InstrumentDef, values: Record<string, string>): boolean {
  return def.items.every(
    (item) => !item.required || !isVisible(item, values) || Boolean(values[item.id]),
  );
}

/** The answers to submit: only items that are shown, so a hidden follow-up is never sent. */
export function visibleAnswers(
  def: InstrumentDef,
  values: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const item of def.items) {
    if (isVisible(item, values) && values[item.id]) out[item.id] = values[item.id];
  }
  return out;
}
