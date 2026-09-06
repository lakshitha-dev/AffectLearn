import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://affectlearn.tech";

// Only public, indexable pages. The rest of the app sits behind authentication.
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: SITE_URL,
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${SITE_URL}/login`,
      changeFrequency: "monthly",
      priority: 0.5,
    },
    {
      url: `${SITE_URL}/register`,
      changeFrequency: "monthly",
      priority: 0.6,
    },
    // The legal pages are public and are what a prospective participant reads before consenting,
    // so they belong in the index rather than being reachable only from the footer.
    ...["privacy", "terms", "data-and-consent", "accessibility"].map((slug) => ({
      url: `${SITE_URL}/legal/${slug}`,
      changeFrequency: "yearly" as const,
      priority: 0.3,
    })),
  ];
}
