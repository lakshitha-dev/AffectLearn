/**
 * Which tracked UI element an interaction happened on, without reading anything it contains.
 *
 * Elements that matter for the research record carry a `data-track` id -- a stable, content-free
 * name such as `nav-next` or `quiz-<blockId>-option-2`. An interaction is attributed to the
 * nearest such ancestor. Text, values and labels are never read, so a click record says WHAT was
 * clicked without saying anything the learner wrote or read.
 */

export const TRACK_ATTR = "data-track";
const MAX_ID_LENGTH = 80;

function elementOf(node: EventTarget | null): Element | null {
  if (typeof Element !== "undefined" && node instanceof Element) return node;
  const parent = (node as Node | null)?.parentElement;
  return parent ?? null;
}

/** The `data-track` id of the nearest tracked ancestor, or undefined if there is none. */
export function trackTarget(node: EventTarget | null): string | undefined {
  const hit = elementOf(node)?.closest(`[${TRACK_ATTR}]`);
  const id = hit?.getAttribute(TRACK_ATTR);
  return id ? id.slice(0, MAX_ID_LENGTH) : undefined;
}

/**
 * True when the interaction is inside a password field or an element marked `data-private`.
 * Such interactions are not recorded at all -- not even their timing or key category.
 */
export function isPrivateTarget(node: EventTarget | null): boolean {
  return Boolean(elementOf(node)?.closest('input[type="password"], [data-private]'));
}
