import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { ThemeProvider } from "@/components/shared/ThemeProvider";
import { QueryProvider } from "@/components/shared/query-provider";
import { GoogleAnalytics } from "@/components/shared/google-analytics";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://affectlearn.tech";
const SITE_NAME = "AffectLearn";
const SITE_DESCRIPTION =
  "AffectLearn is an adaptive e-learning platform that senses when you're engaged, confused, bored, or frustrated — using your webcam and reading behavior — and reshapes each lesson in real time with hints, challenges, and breaks. No video is ever stored.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "AffectLearn — Adaptive learning that responds to how you feel",
    template: "%s · AffectLearn",
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: [
    "adaptive learning",
    "affect detection",
    "emotion-aware e-learning",
    "personalized learning platform",
    "engagement detection",
    "facial affect recognition",
    "online courses",
    "EdTech",
  ],
  authors: [{ name: SITE_NAME }],
  creator: SITE_NAME,
  publisher: SITE_NAME,
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: "AffectLearn — Adaptive learning that responds to how you feel",
    description: SITE_DESCRIPTION,
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "AffectLearn — Adaptive learning that responds to how you feel",
    description: SITE_DESCRIPTION,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large" },
  },
  category: "education",
};

// Site-wide structured data (Organization + WebSite) for rich results.
const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "EducationalOrganization",
      "@id": `${SITE_URL}/#organization`,
      name: SITE_NAME,
      url: SITE_URL,
      description: SITE_DESCRIPTION,
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      url: SITE_URL,
      name: SITE_NAME,
      description: SITE_DESCRIPTION,
      publisher: { "@id": `${SITE_URL}/#organization` },
      inLanguage: "en",
    },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} ${jetbrainsMono.variable} antialiased`} suppressHydrationWarning>
        {/* JSON-LD rendered in the body (App Router-safe); search engines still read it.
            A manual <head> here caused hydration mismatches that amplified guard redirects. */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
        <GoogleAnalytics />
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <QueryProvider>
            {children}
            {/*
              Story 5.7: the single shared `sonner` toast viewport for the whole app. Moved to
              bottom-right per the Epic-5 AC + UX spec (line 1099 puts ALL success toasts
              bottom-right; this also moves the designer/auth/onboarding toasts there — see
              Open Question #4). System/notification toasts (`notification` + `system.*`) are
              enqueued through `lib/toast-controller` (max-2 visible / 500ms-queued; success/
              info/warning auto-dismiss 3s, errors persist via `closeButton`). `richColors`
              gives the severity coloring; `role`/`aria-live` per severity is provided by
              sonner (status/polite for normal toasts, alert/assertive for errors). The
              lesson-view webcam indicator pill also sits bottom-right but is small and
              persistent — transient toasts render above it briefly (acceptable; the indicator
              is not restructured here). `visibleToasts={2}` is a belt-and-suspenders cap; the
              controller remains the source of truth for the 500ms FIFO spacing.
            */}
            <Toaster position="bottom-right" richColors closeButton visibleToasts={2} />
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
