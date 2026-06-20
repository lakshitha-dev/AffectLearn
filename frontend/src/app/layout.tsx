import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { ThemeProvider } from "@/components/shared/ThemeProvider";
import { QueryProvider } from "@/components/shared/query-provider";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: "AffectLearn",
  description: "Adaptive e-learning platform with real-time affect detection",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} ${jetbrainsMono.variable} antialiased`} suppressHydrationWarning>
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
