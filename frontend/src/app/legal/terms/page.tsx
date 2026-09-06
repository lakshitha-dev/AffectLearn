import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of service",
  description: "The terms on which AffectLearn is provided.",
};

export default function TermsPage() {
  return (
    <>
      <h1>Terms of service</h1>
      <p className="!text-slate-500 !text-[14px]">Last updated 6 September 2026</p>

      <p>
        AffectLearn is an adaptive learning platform built as an academic research project. Using
        it means accepting these terms. They are short because the service is small.
      </p>

      <h2>What this is</h2>
      <p>
        A research platform offered free of charge. It is not a commercial product, carries no
        service-level guarantee, and may be taken offline, reset or changed without notice. Do not
        rely on it as the sole record of work that matters to you.
      </p>

      <h2>Your account</h2>
      <ul>
        <li>You need a verified email address, and you are responsible for what happens under it.</li>
        <li>One account per person. Do not share credentials.</li>
        <li>
          We may suspend an account that is used to attack the service, to access another
          person&apos;s data, or to disrupt other learners.
        </li>
      </ul>

      <h2>Course content</h2>
      <p>
        Course material is provided for learning. Designers retain rights in the material they
        author, and a designer may edit or remove only their own courses. Seeded course material
        belongs to the project.
      </p>
      <p>
        If you author content here, you keep it, and you grant us permission to store, display and
        adapt it for the purpose of running the platform.
      </p>

      <h2>Acceptable use</h2>
      <ul>
        <li>Do not attempt to access another learner&apos;s records.</li>
        <li>Do not probe, scan or overload the service.</li>
        <li>Do not upload unlawful material, or material you do not have the rights to.</li>
        <li>
          Do not attempt to re-identify participants from any aggregate or exported research data.
        </li>
      </ul>

      <h2>Adaptive features</h2>
      <p>
        The platform will sometimes offer a hint, a suggestion to move on, or a suggestion to take
        a break. These are suggestions. They are generated automatically, they are sometimes
        wrong, and you can dismiss any of them. They are not academic advice, and they are not a
        judgement of your ability. See{" "}
        <a href="/legal/data-and-consent">Data &amp; consent</a> for what the system can and
        cannot actually detect.
      </p>

      <h2>Availability and liability</h2>
      <p>
        The service is provided as-is and as-available, without warranties of any kind. To the
        extent permitted by law, the project and its authors are not liable for loss arising from
        use of the platform, including loss of data or of learning progress.
      </p>

      <h2>Ending your use</h2>
      <p>
        You can stop using AffectLearn at any time and request deletion of your data — see{" "}
        <a href="/legal/privacy">the privacy policy</a>. We may end access to the service for
        everyone when the research project concludes.
      </p>

      <h2>Changes</h2>
      <p>Material changes to these terms will be posted here and dated.</p>

      <h2>Contact</h2>
      <p>
        <a href="mailto:privacy@affectlearn.tech">privacy@affectlearn.tech</a>.
      </p>
    </>
  );
}
