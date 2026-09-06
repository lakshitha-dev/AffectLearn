import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy policy",
  description:
    "What AffectLearn captures, what it never captures, how long it is kept, and how to have it deleted.",
};

/**
 * The claims here are written to match the code, not the marketing page.
 *
 * Deletion and the 90-day retention limit were both honoured by hand when this page was first
 * written, and it said so. Both are now implemented — self-service erasure from the profile, and
 * a scheduled retention sweep — so the wording was changed to match the code rather than left
 * describing a system that no longer exists. Keep it that way: a policy is only worth anything
 * if it tracks what actually happens.
 */
export default function PrivacyPolicyPage() {
  return (
    <>
      <h1>Privacy policy</h1>
      <p className="!text-slate-500 !text-[14px]">Last updated 6 September 2026</p>

      <p>
        AffectLearn adapts a lesson to how you are getting on with it. Doing that means observing
        how you work, so this page sets out exactly what is observed, what is stored, and what is
        never stored. Where something is a promise we keep by hand rather than by code, it says so.
      </p>

      <h2>What we never store</h2>
      <p>
        <strong>Webcam video and images never leave your browser.</strong> If you turn the camera
        on, your device measures a small set of geometric quantities from each frame — where your
        gaze is directed, whether your mouth is open, how much you are moving — and sends only
        those numbers. That is roughly 600 bytes per 30-second cycle. No frame, crop or still
        image is transmitted, written to disk, or seen by a person, and the system that processes
        a cycle is deliberately built without the ability to save one.
      </p>
      <p>
        <strong>We never capture what you type.</strong> Keystrokes are counted by category — a
        letter, a number, a backspace — and the characters themselves are discarded at the point
        of capture. Your answers to quizzes are stored, because they are your work; the raw
        keystrokes that produced them are not.
      </p>

      <h2>What we do store</h2>
      <ul>
        <li>
          <strong>Your account:</strong> name, email address, and — if you gave them — an age
          range and degree programme.
        </li>
        <li>
          <strong>Your learning:</strong> courses you enrol in, sections you open and finish, how
          long you spend, quiz and assessment answers, and every attempt at them rather than only
          the first.
        </li>
        <li>
          <strong>Aggregate interaction signals:</strong> summary statistics over 30-second
          windows of mouse movement, scrolling and typing rhythm — speeds, counts, pauses,
          measures of how erratic the movement is. Not the paths, not the keys.
        </li>
        <li>
          <strong>Facial geometry readings</strong>, if the camera is on: the derived numbers
          described above, and the model&apos;s output for that cycle.
        </li>
        <li>
          <strong>Help you were offered:</strong> each hint or suggestion, what it said, whether
          you accepted or dismissed it, and how you answered next.
        </li>
        <li>
          <strong>Anything you tell us directly:</strong> your own reports of how a section felt,
          and questionnaire or survey answers.
        </li>
      </ul>

      <h2>You can turn the camera off</h2>
      <p>
        The camera is optional and can be switched off at any time from your profile, or refused
        at the start. The platform continues to work in behavioural-only mode, reading how you
        move through the material instead. A visible indicator tells you which mode you are in
        whenever detection is running.
      </p>

      <h2>How your data is used</h2>
      <p>
        To adapt lessons to you while you study, to show you your own progress, to show course
        designers where learners in aggregate struggle, and — for research participants — to
        answer the research questions described in{" "}
        <a href="/legal/data-and-consent">Data &amp; consent</a>.
      </p>
      <p>
        We do not sell your data, do not use it for advertising, and do not link it to advertising
        profiles.
      </p>

      <h2>Who can see it</h2>
      <p>
        Research records are keyed to an opaque identifier rather than your name or email. This is
        pseudonymisation, not anonymisation, and the distinction matters: an administrator with
        access to both the account table and the research records could join them. Identifying
        fields are never included in a research export. Course designers see aggregates across
        learners, never one learner&apos;s record.
      </p>

      <h2>How long it is kept, and how to have it deleted</h2>
      <p>
        <strong>You can delete your account and everything recorded about you yourself, from your
        profile.</strong> It takes effect immediately, it does not go through us, and you do not
        have to give a reason. You will be asked for your password and to type DELETE, because it
        cannot be undone. Deletion removes your account, your learning records, the interaction
        signals, and the research event log — you will be shown exactly how many rows were removed
        from each.
      </p>
      <p>
        <strong>You can also download everything we hold about you</strong> before deciding. The
        export is deliberately complete rather than curated: it includes the interaction telemetry
        and the research records, not just the parts that are easy to read.
      </p>
      <p>
        <strong>Research records are automatically deleted after 90 days.</strong> This runs as a
        scheduled job rather than as a promise someone remembers to keep. Your account and your
        own course progress are not covered by that limit — those are yours until you delete them.
      </p>
      <p>
        If you would rather someone did it for you, or you have lost access to your account, email{" "}
        <a href="mailto:privacy@affectlearn.tech">privacy@affectlearn.tech</a> from the address on
        your account and we will act within 24 hours.
      </p>

      <h2>Security</h2>
      <p>
        Traffic between your browser and AffectLearn is encrypted in transit, and stored data is
        encrypted at rest by our hosting provider. Access to production data is limited to the
        project team.
      </p>

      <h2>Changes</h2>
      <p>
        If this policy changes in a way that affects what is collected or how long it is kept, we
        will say so on this page and date the change.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about any of this go to{" "}
        <a href="mailto:privacy@affectlearn.tech">privacy@affectlearn.tech</a>.
      </p>
    </>
  );
}
