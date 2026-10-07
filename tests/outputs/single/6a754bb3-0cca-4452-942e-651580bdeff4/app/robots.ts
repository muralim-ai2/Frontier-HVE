import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/seo";

/** Robots rules pointing to the sitemap. */
export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", allow: "/" }, sitemap: `${SITE_URL}/sitemap.xml` };
}
