// Correct labels for a model's softmax output, per modality.
//
// THE TWO MODALITIES USE DIFFERENT CLASS ORDERS. From the backend:
//   behavioural  BEHAVIORAL_CLASS_ORDER = ("engaged", "bored", "confused", "frustrated")
//   facial       AFFECT_CLASS_ORDER     = ("bored", "confused", "engaged", "frustrated")
//
// `ws.py` forwards each model's `probs` array verbatim, so a single shared label list cannot
// be correct for both. The monitor previously labelled BOTH with the facial order, which meant
// every behavioural distribution bar was mislabelled — probs[0] is `engaged` but was drawn as
// `bored`. These helpers keep each modality's order with the payload it belongs to.
//
// Binary-confusion heads emit 2 slots ([1-p, p]) and get their own names.

import { DETECTABLE_AFFECTS } from "./shared";

export const BEHAVIORAL_PROB_ORDER = ["engaged", "bored", "confused", "frustrated"] as const;
export const FACIAL_PROB_ORDER = ["bored", "confused", "engaged", "frustrated"] as const;
export const BINARY_PROB_ORDER = ["not confused", "confused"] as const;

export interface Distribution {
  probs: number[];
  labels: string[];
}

const DETECTABLE: readonly string[] = DETECTABLE_AFFECTS;

/**
 * Zip probs with `order`, then drop the states the deployed models cannot emit.
 *
 * `bored` and `frustrated` are pinned to 0.0 server-side, so showing them would draw two
 * permanently-empty bars that read as "this learner was never bored" rather than "boredom is
 * not measurable here".
 */
function detectableOnly(probs: number[], order: readonly string[]): Distribution {
  const out: Distribution = { probs: [], labels: [] };
  order.forEach((label, i) => {
    if (i < probs.length && DETECTABLE.includes(label)) {
      out.labels.push(label);
      out.probs.push(probs[i]);
    }
  });
  return out;
}

/** A 2-slot head is already binary confusion — both slots are meaningful, keep both. */
function binary(probs: number[]): Distribution {
  return { probs: probs.slice(0, 2), labels: [...BINARY_PROB_ORDER] };
}

export function behavioralDistribution(probs?: number[] | null): Distribution | null {
  if (!probs || probs.length === 0) return null;
  if (probs.length === 2) return binary(probs);
  return detectableOnly(probs, BEHAVIORAL_PROB_ORDER);
}

export function facialDistribution(probs?: number[] | null): Distribution | null {
  if (!probs || probs.length === 0) return null;
  if (probs.length === 2) return binary(probs);
  return detectableOnly(probs, FACIAL_PROB_ORDER);
}
