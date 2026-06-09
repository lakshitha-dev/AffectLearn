/**
 * categoriseKey — map a `KeyboardEvent.key` value to a privacy-safe category.
 *
 * PRIVACY CONTRACT (Story 4.3 AC #6): this is the ONLY place `event.key` is
 * inspected. The raw character is read to compute the discriminator and then
 * discarded — it is never stored, logged, or returned. For letter/digit keys
 * the function returns a bucket name (`"alpha"` / `"digit"`), NOT the character.
 *
 * Pure function: no side effects, no global state, no console output.
 */

import type { KeyCategory } from "@/types/behavioral-events";

export function categoriseKey(key: string): KeyCategory {
  // Single printable letter — bucket as alpha WITHOUT capturing which letter.
  if (/^[a-zA-Z]$/.test(key)) return "alpha";
  // Single digit — bucket as digit WITHOUT capturing which digit.
  if (/^[0-9]$/.test(key)) return "digit";

  switch (key) {
    case " ":
    case "Tab":
      return "whitespace";
    case "Backspace":
    case "Delete":
      return "backspace";
    case "Enter":
      return "enter";
    case "Shift":
    case "Control":
    case "Alt":
    case "Meta":
    case "AltGraph":
      return "modifier";
    case "ArrowUp":
    case "ArrowDown":
    case "ArrowLeft":
    case "ArrowRight":
    case "Home":
    case "End":
    case "PageUp":
    case "PageDown":
      return "navigation";
    default:
      // F-keys, dead keys, IME composition keys, punctuation, etc. The raw
      // value is intentionally NOT propagated — everything else is "other".
      return "other";
  }
}
