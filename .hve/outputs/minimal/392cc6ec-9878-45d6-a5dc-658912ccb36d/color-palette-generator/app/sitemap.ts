import type { MetadataRoute } from "next";
import { siteUrl } from "../lib/seo";
/** List the public canonical pages. */
export default function sitemap(): MetadataRoute.Sitemap { return ["", "/privacy", "/terms"].map((path: string): MetadataRoute.Sitemap[number] => ({ url: `${siteUrl}${path}` })); }
