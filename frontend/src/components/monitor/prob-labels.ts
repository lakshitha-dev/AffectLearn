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

import { BEHAVIORAL_DETECTABLE, DETECTABLE_AFFECTS } from "./shared";

export const BEHAVIORAL_PROB_ORDER = ["engaged", "bored", "confused", "frustrated"] as const;
export const FACIAL_PROB_ORDER = ["bored", "confused", "engaged", "frustrated"] as const;
/**
 * Class order of a two-slot facial head, BY MODEL KIND.
 *
 * Both deployed binary artifacts emit two probabilities and index 1 means a different construct
 * in each: P(confused) for the DAiSEE model, P(disengaged) for the geometry model. Labelling
 * every 2-slot head "not confused / confused" drew the geometry channel's boredom probability as
 * a 95% `confused` bar — a plausible-looking chart of the wrong quantity.
 */
export const BINARY_PROB_ORDER = ["not confused", "confused"] as const;
export const GEOMETRY_PROB_ORDER = ["engaged", "bored"] as const;

export interface Distribution {
  probs: number[];
  labels: string[];
}

const DETECTABLE: readonly string[] = DETECTABLE_AFFECTS;
const BEHAVIORAL_ONLY: readonly string[] = BEHAVIORAL_DETECTABLE;

/**
 * Zip probs with `order`, then drop the states the deployed models cannot emit.
 *
 * `bored` and `frustrated` are pinned to 0.0 server-side, so showing them would draw two
 * permanently-empty bars that read as "this learner was never bored" rather than "boredom is
 * not measurable here".
 */
function detectableOnly(
  probs: number[],
  order: readonly string[],
  keep: readonly string[] = DETECTABLE,
): Distribution {
  const out: Distribution = { probs: [], labels: [] };
  order.forEach((label, i) => {
    if (i < probs.length && keep.includes(label)) {
      out.labels.push(label);
      out.probs.push(probs[i]);
    }
  });
  return out;
}

/**
 * A 2-slot head: both slots are meaningful, so keep both. The LABELS depend on which artifact
 * produced it, which is why `modelKind` is threaded through rather than inferred from the width.
 */
function binary(probs: number[], modelKind?: string | null): Distribution {
  const labels = modelKind === "geometry" ? GEOMETRY_PROB_ORDER : BINARY_PROB_ORDER;
  return { probs: probs.slice(0, 2), labels: [...labels] };
}

export function behavioralDistribution(probs?: number[] | null): Distribution | null {
  if (!probs || probs.length === 0) return null;
  if (probs.length === 2) return binary(probs);
  return detectableOnly(probs, BEHAVIORAL_PROB_ORDER, BEHAVIORAL_ONLY);
}

export function facialDistribution(
  probs?: number[] | null,
  modelKind?: string | null,
): Distribution | null {
  if (!probs || probs.length === 0) return null;
  if (probs.length === 2) return binary(probs, modelKind);
  return detectableOnly(probs, FACIAL_PROB_ORDER);
}
