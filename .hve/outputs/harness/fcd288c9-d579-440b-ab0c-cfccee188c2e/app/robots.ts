import type { MetadataRoute } from "next";
/** Return crawler directives. */
export default function robots(): MetadataRoute.Robots { return { rules: { userAgent: "*", allow: "/" }, sitemap: "https://colorpalettegenerator.example/sitemap.xml" }; }