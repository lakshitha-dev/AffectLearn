import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Data & consent",
  description:
    "What AffectLearn is researching, what taking part involves, and what the system can and cannot detect.",
};

/**
 * The page a participant should be able to read before consenting, and the one that states the
 * system's limits without a marketing filter.
 *
 * The "what it cannot do" section is here deliberately. Two of the four affect states the
 * literature names have no detector in this system, the deployed reasoning layer is a rule map
 * rather than the fine-tuned model, and no learner trial has run. A consent page that omitted
 * any of that would be describing a different system.
 */
export default function DataAndConsentPage() {
  return (
    <>
      <h1>Data &amp; consent</h1>
      <p className="!text-slate-500 !text-[14px]">Last updated 6 September 2026</p>

      <p>
        AffectLearn is a research platform as well as a learning one. It exists to test whether a
        system that notices when a learner is struggling, and responds, helps them more than one
        that does not. This page explains what that means for you.
      </p>

      <h2>What is being studied</h2>
      <p>
        Three questions. Which signs of confusion or drifting attention can actually be detected
        from a webcam and from how someone works. Whether combining those signals beats using the
        better one alone. And whether responding to them improves what a learner takes away from
        a lesson.
      </p>

      <h2>What taking part involves</h2>
      <ul>
        <li>Working through course material as you normally would.</li>
        <li>
          Occasionally being asked how a section felt. You can skip any of these, and some are
          deliberately not shown at all so we can tell whether being asked changes how people
          behave.
        </li>
        <li>A short questionnaire before you start and a short survey at the end.</li>
        <li>Optionally, having the camera on. Declining changes nothing about your access.</li>
      </ul>
      <p>
        Some material is written to be harder going than the rest, and some to be deliberately
        plain. That is part of the design rather than a flaw in the course, and there is a
        debrief at the end explaining which was which.
      </p>

      <h2>What the system cannot do</h2>
      <p>
        Stated plainly, because it is easy to imply more than is true and we would rather not.
      </p>
      <ul>
        <li>
          <strong>It detects two states, not four.</strong> Confusion, from how you work; drifting
          attention, from the camera. Frustration and boredom-as-an-emotion have no detector here
          that we would stand behind, so the system does not claim to see them.
        </li>
        <li>
          <strong>It is often wrong.</strong> The detectors score well below certainty. That is
          why help is offered rather than imposed, why the system waits for a signal to persist
          before acting, and why it stays quiet when it is unsure.
        </li>
        <li>
          <strong>The reasoning behind a hint is currently a set of rules.</strong> A fine-tuned
          language model was trained for this role and evaluated offline, but the production
          service runs without the hardware to host it, so a deterministic rule map chooses the
          response instead.
        </li>
        <li>
          <strong>Whether any of this improves learning is unmeasured.</strong> The trial that
          would answer it has not been run. Nothing here should be read as a claim that it does.
        </li>
      </ul>

      <h2>Your rights</h2>
      <ul>
        <li>Taking part is voluntary, and declining costs you nothing.</li>
        <li>
          You can withdraw at any point without giving a reason, including after finishing.
        </li>
        <li>
          You can delete your data yourself, from your profile, and see exactly what was
          removed. See <a href="/legal/privacy">the privacy policy</a> for what that covers.
        </li>
        <li>You can ask what has been recorded about you and receive a copy.</li>
      </ul>

      <h2>How records are kept</h2>
      <p>
        Research records carry an opaque identifier rather than your name or email, and
        identifying fields are never included in an export. This is pseudonymisation rather than
        anonymisation — an administrator with access to both tables could join them — and we
        describe it accurately rather than calling it anonymous.
      </p>

      <h2>Ethical review</h2>
      <p>
        This project was carried out as an individual final-year research project and its design,
        including the webcam analysis and the interaction logging, was reviewed and authorised by
        the project supervisor. No separate ethics committee reference was issued. We record that
        here rather than leaving it to be assumed, because the work processes facial imagery of
        student participants and the basis on which it proceeds should be legible to you.
      </p>

      <h2>Contact</h2>
      <p>
        Questions, or a request to withdraw:{" "}
        <a href="mailto:privacy@affectlearn.tech">privacy@affectlearn.tech</a>.
      </p>
    </>
  );
}
