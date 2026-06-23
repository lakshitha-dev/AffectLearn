import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://affectlearn.tech";

// Authenticated app sections — no SEO value (they redirect to /login) and shouldn't
// consume crawl budget. The public surface is the landing page + auth entry points.
const PRIVATE_PATHS = [
  "/courses",
  "/analytics",
  "/users",
  "/onboarding",
  "/profile",
  "/progress",
  "/dashboard",
  "/content-editor",
  "/courses-editor",
  "/editor",
  "/ab-groups",
  "/admin-settings",
  "/data-export",
  "/monitor",
  "/system-health",
  "/settings",
  "/study",
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: PRIVATE_PATHS,
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
