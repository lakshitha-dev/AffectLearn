/**
 * Behavioral signal event schema (Story 4.3).
 *
 * The hook (`use-behavioral-signals.ts`) ships RAW timed events; the backend
 * (Story 4.4b) extracts the Bi-LSTM features via the shared
 * `feature_engineering.py`. See `ml-training-guide-behavioral.md` §6-7 for the
 * train/serve-consistency argument behind this raw-event contract.
 *
 * Wire contract notes:
 *   - All field names are snake_case (architecture.md line 489 — the WS protocol
 *     exception to the REST camelCase rule). TypeScript does not enforce this,
 *     so keep it manually consistent with the backend Pydantic schema.
 *   - Every event carries BOTH a monotonic (`t_mono`, performance.now()) and a
 *     wall-clock (`t_wall`, Date.now()) timestamp. Monotonic is jitter-free for
 *     timestep alignment; wall-clock is for cross-system correlation with the
 *     facial-features stream (Story 4.2).
 *
 * PRIVACY: there is deliberately NO `key` field on `KeyEvent`. The raw character
 * typed is never serialised — only its `category` (see `key-category.ts`).
 */

export interface BaseEvent {
  t_mono: number; // performance.now() — monotonic milliseconds since hook mount
  t_wall: number; // Date.now() — Unix milliseconds (UTC)
}

/**
 * Key categories. Letters and digits are bucketed WITHOUT their content
 * (privacy contract, AC #6); backspace/enter ARE named because the Bi-LSTM uses
 * them as features (`backspace_pct`, `pause_count`).
 */
export type KeyCategory =
  | "alpha" // a-z, A-Z          (content NOT captured)
  | "digit" // 0-9               (content NOT captured)
  | "whitespace" // space, tab
  | "backspace"
  | "enter"
  | "modifier" // shift, ctrl, alt, meta
  | "navigation" // arrows, home, end, pageup, pagedown
  | "other"; // any other key — bucketed

export interface MouseSample extends BaseEvent {
  kind: "mouse_sample";
  x: number; // viewport X (CSS pixels) — normalised server-side per learner
  y: number; // viewport Y (CSS pixels)
}

export interface MouseClick extends BaseEvent {
  kind: "mouse_click";
  x: number;
  y: number;
  button: 0 | 1 | 2; // left | middle | right
  /** `data-track` id of the element clicked (see `lib/track-target.ts`). Never text. */
  target?: string;
}

export interface KeyEvent extends BaseEvent {
  kind: "key";
  category: KeyCategory;
  // NOTE: no `key` field. The raw character is never serialised. See AC #6.
}

export interface ScrollEvent extends BaseEvent {
  kind: "scroll";
  scroll_y: number; // window.scrollY at moment of event
  delta_y: number; // wheel deltaY (0 for native scroll events)
  direction: "up" | "down" | "none"; // computed from delta sign or scrollY change
}

export interface VisibilityEvent extends BaseEvent {
  kind: "visibility";
  state: "visible" | "hidden"; // page visibility — useful for `idle_time_pct` calc
}

export type BehavioralEvent =
  | MouseSample
  | MouseClick
  | KeyEvent
  | ScrollEvent
  | VisibilityEvent;

/**
 * Interaction context that is NOT a model input (schema v2).
 *
 * Kept out of `events` on purpose: the server's feature extraction reads `events` only, so these
 * can be recorded for research without changing a single value the deployed model is given.
 */
export interface HoverEvent {
  kind: "hover";
  /** `data-track` id of the element the pointer rested on. */
  target: string;
  enter_t_wall: number;
  dwell_ms: number;
}

export interface ClipboardUiEvent {
  kind: "clipboard";
  action: "copy" | "cut" | "paste";
  /** Where it happened. The clipboard CONTENT is never read. */
  target?: string;
  t_wall: number;
}

export type UiEvent = HoverEvent | ClipboardUiEvent;

/** The page geometry the coordinates in this window refer to. */
export interface ViewportInfo {
  w: number; // window.innerWidth (CSS px)
  h: number; // window.innerHeight
  doc_h: number; // document height, for scroll depth
  dpr: number; // devicePixelRatio
}

/**
 * Cheap client-side aggregates (AC #4). NOT the Bi-LSTM input feature vector —
 * these integers let the backend cross-check its own feature extraction and let
 * Story 4.4c's fusion fall back gracefully if the backend extractor is down.
 */
export interface BehavioralWindowSummary {
  mouse_sample_count: number; // expected ~300 (30s × 10Hz) for a non-idle window
  mouse_click_count: number;
  keystroke_count: number;
  backspace_count: number;
  scroll_event_count: number;
  visibility_hidden_ms: number; // total time `document.visibilityState === "hidden"`
  idle: boolean; // true if no mouse samples, keystrokes, or scrolls in the window
}

/**
 * The full `data` payload of a `behavioral_window` WS message (AC #4).
 */
export interface BehavioralWindowPayload {
  cycle_number: number; // monotonic from 1, increments per cycle
  capture_started_at_mono: number; // performance.now() of window start
  capture_ended_at_mono: number; // performance.now() of window end
  capture_started_at_wall: number; // Date.now() of window start
  capture_ended_at_wall: number; // Date.now() of window end
  window_duration_ms: number; // 30000
  sampling_rate_hz: number; // 10
  schema_version: number; // bumps if behavioral-events.ts breaking-changes

  // Raw events, ordered by t_mono ascending. The backend extracts features.
  events: BehavioralEvent[];

  summary: BehavioralWindowSummary;

  // Dropped-event counter — see AC #9 (NFR9: <1% loss)
  dropped_events: number;

  /**
   * The section the learner is on, so the server can ground the adaptation prompts in the
   * material actually on screen (`services/content_context_service`). Optional: a cycle with
   * no section still runs affect detection normally, it just yields a generic hint.
   */
  section_id?: string;

  // ── schema v2: research context, not model input ──
  /** One id per lesson-page mount, so windows from two visits to a page are distinguishable. */
  page_instance_id?: string;
  viewport?: ViewportInfo;
  ui_events?: UiEvent[];
}

/**
 * Debug-only metrics (AC #10). Exposed via the hook's returned ref in dev only;
 * never sent over the wire.
 */
export interface BehavioralDebug {
  eventsPerSecond: number; // rolling counter across the current cycle
  aggregatorTickCount: number; // should be ~300 per 30s cycle (10 Hz × 30s)
  aggregatorMissedTicks: number; // must be < 3 per cycle for NFR9 compliance
  lastCycleDroppedEvents: number; // events dropped due to AC #9 buffer cap
  lastCycleMessageBytes: number; // size of last sent WS message body
}

/**
 * Compile-time exhaustiveness helper for `BehavioralEvent` switches (AC #12).
 * A `switch (e.kind)` that handles every variant narrows the default branch to
 * `never`; passing that branch here is a no-op at runtime but a type error if a
 * new event variant is added without a matching case.
 */
export function assertNever(_: never): never {
  throw new Error("unreachable");
}
