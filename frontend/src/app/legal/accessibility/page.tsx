import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Accessibility",
  description:
    "What AffectLearn does for accessibility today, what it has not yet been tested against, and how to report a barrier.",
};

/**
 * An accessibility statement is only worth publishing if it distinguishes what has been TESTED
 * from what has merely been INTENDED. No formal audit has been carried out here, so this page
 * says that outright rather than implying conformance it cannot evidence.
 */
export default function AccessibilityPage() {
  return (
    <>
      <h1>Accessibility</h1>
      <p className="!text-slate-500 !text-[14px]">Last updated 6 September 2026</p>

      <p>
        This statement covers affectlearn.tech. It separates what has been built and checked from
        what has not yet been formally tested, because a statement that blurs the two is not
        useful to anyone deciding whether they can use the site.
      </p>

      <h2>What is in place</h2>
      <ul>
        <li>
          <strong>The camera is never required.</strong> Every feature works in behavioural-only
          mode, so nothing here depends on a face being visible to a camera or on any particular
          facial expression.
        </li>
        <li>
          <strong>Adaptations do not steal focus.</strong> Hints appear beside the content rather
          than as modal pop-ups, nothing auto-advances the lesson, and every suggestion can be
          dismissed.
        </li>
        <li>
          <strong>Motion is reduced on request.</strong> The interface honours the operating
          system&apos;s &ldquo;reduce motion&rdquo; setting, and animated content on the marketing
          page stops when it is set.
        </li>
        <li>
          <strong>A distraction-free reading mode.</strong> Pressing <kbd>F</kbd> in a lesson
          hides surrounding interface so only the material remains.
        </li>
        <li>
          <strong>Semantic structure.</strong> Interface components are built on accessible
          primitives that carry roles, labels and keyboard behaviour, and data views such as the
          affect heatmap expose a grid structure to assistive technology.
        </li>
        <li>
          <strong>Text scales.</strong> Layouts use relative units and reflow rather than breaking
          when text is enlarged.
        </li>
      </ul>

      <h2>What has not been tested</h2>
      <p>
        <strong>No formal accessibility audit has been carried out, and we do not claim
        conformance to WCAG at any level.</strong> In particular, the following have not been
        systematically verified:
      </p>
      <ul>
        <li>End-to-end screen-reader journeys through the lesson player and the assessments.</li>
        <li>Complete keyboard-only navigation, including the analytics and monitor views.</li>
        <li>Colour-contrast ratios across every state of every component.</li>
        <li>The rendered diagram and code blocks inside course content.</li>
      </ul>
      <p>
        Some of these are likely to be fine and some are likely not. We would rather name them
        than let a general assurance imply that all of them have been checked.
      </p>

      <h2>Known limitations</h2>
      <ul>
        <li>
          The interface is available in English only. There is no language switching.
        </li>
        <li>
          Course content includes diagrams whose text alternatives have not been reviewed for
          completeness.
        </li>
        <li>
          The administrative monitor is a dense, real-time data view and has been built for
          sighted use at a desk.
        </li>
      </ul>

      <h2>Reporting a barrier</h2>
      <p>
        If something here stops you using the platform, please tell us — it is the fastest way for
        it to get fixed, and reports are prioritised over the audit backlog. Email{" "}
        <a href="mailto:accessibility@affectlearn.tech">accessibility@affectlearn.tech</a> with the
        page and what happened, and we will reply.
      </p>
    </>
  );
}
