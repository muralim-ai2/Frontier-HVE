import type { MetadataRoute } from "next";
/** Return public application routes. */
export default function sitemap(): MetadataRoute.Sitemap { return ["", "/privacy", "/terms"].map((path) => ({ url: `https://colorpalettegenerator.example${path}`, lastModified: new Date() })); }