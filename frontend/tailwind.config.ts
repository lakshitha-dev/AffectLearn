import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  // Affect-heatmap intensity classes (Story 7.3). These are emitted as full
  // static strings from src/components/designer/heatmap-intensity.ts, but are
  // safelisted as belt-and-suspenders against the Tailwind purge so the cell
  // backgrounds always render.
  safelist: [
    "bg-affect-engaged/15",
    "bg-affect-engaged/35",
    "bg-affect-engaged/65",
    "bg-affect-engaged/100",
    "bg-affect-confused/15",
    "bg-affect-confused/35",
    "bg-affect-confused/65",
    "bg-affect-confused/100",
    "bg-affect-bored/15",
    "bg-affect-bored/35",
    "bg-affect-bored/65",
    "bg-affect-bored/100",
    "bg-affect-frustrated/15",
    "bg-affect-frustrated/35",
    "bg-affect-frustrated/65",
    "bg-affect-frustrated/100",
    // Story 7.4 — section-detail affect bars + content hotspots.
    "bg-affect-engaged",
    "bg-affect-confused",
    "bg-affect-bored",
    "bg-affect-frustrated",
    "bg-affect-confused/10",
    "bg-affect-confused/20",
    "border-affect-confused",
    "text-affect-engaged",
    "text-affect-confused",
    "text-affect-bored",
    "text-affect-frustrated",
    "focus-visible:ring-affect-confused",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          foreground: "rgb(var(--primary-foreground) / <alpha-value>)",
          soft: "rgb(var(--primary-soft) / <alpha-value>)",
        },
        secondary: "rgb(var(--secondary) / <alpha-value>)",
        muted: {
          DEFAULT: "rgb(var(--muted) / <alpha-value>)",
          foreground: "rgb(var(--muted-foreground) / <alpha-value>)",
        },
        background: "rgb(var(--background) / <alpha-value>)",
        foreground: "rgb(var(--foreground) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        input: "rgb(var(--input) / <alpha-value>)",
        ring: "rgb(var(--ring) / <alpha-value>)",
        card: {
          DEFAULT: "rgb(var(--card) / <alpha-value>)",
          foreground: "rgb(var(--card-foreground) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          foreground: "rgb(var(--accent-foreground) / <alpha-value>)",
        },
        destructive: {
          DEFAULT: "rgb(var(--destructive) / <alpha-value>)",
          foreground: "rgb(var(--destructive-foreground) / <alpha-value>)",
        },
        success: "rgb(var(--success) / <alpha-value>)",
        warning: "rgb(var(--warning) / <alpha-value>)",
        error: "rgb(var(--error) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
        affect: {
          engaged: "rgb(var(--affect-engaged) / <alpha-value>)",
          confused: "rgb(var(--affect-confused) / <alpha-value>)",
          bored: "rgb(var(--affect-bored) / <alpha-value>)",
          frustrated: "rgb(var(--affect-frustrated) / <alpha-value>)",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
