import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/seo";

/** Sitemap listing the home, privacy, and terms pages. */
export default function sitemap(): MetadataRoute.Sitemap {
  return ["", "/privacy", "/terms"].map((path) => ({ url: `${SITE_URL}${path}`, changeFrequency: "monthly", priority: path === "" ? 1 : 0.3 }));
}
