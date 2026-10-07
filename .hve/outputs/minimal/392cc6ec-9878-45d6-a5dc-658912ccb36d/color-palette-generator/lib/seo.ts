/** Shared site metadata and public frequently asked questions. */
const configuredUrl = process.env.NEXT_PUBLIC_SITE_URL;
if (!configuredUrl) throw new Error("Set NEXT_PUBLIC_SITE_URL to the public site origin.");
const parsedUrl = new URL(configuredUrl);
if (!["http:", "https:"].includes(parsedUrl.protocol) || parsedUrl.username || parsedUrl.password || parsedUrl.pathname !== "/" || parsedUrl.search || parsedUrl.hash) throw new Error("NEXT_PUBLIC_SITE_URL must be an HTTP(S) origin without a path, credentials, query, or fragment.");
export const siteUrl = parsedUrl.origin;
export const title = "Color Palette Generator | Create Beautiful Color Schemes";
export const description = "Generate beautiful color palettes for websites, brands, apps, and creative projects. Copy HEX, RGB, HSL, CSS variables, Tailwind config, and more.";
export const faq: [string, string][] = [
  ["What is a color palette generator?", "A tool for creating coordinated color combinations for creative projects."],
  ["Can I use these palettes for commercial projects?", "Yes. Colors are not exclusive, and palettes are not legal brand advice. Check your project's requirements."],
  ["Are the generated palettes accessible?", "Not automatically. Contrast depends on the foreground, background, text size, and surrounding design. Verify your final layouts."],
  ["What color formats does this tool support?", "HEX, RGB, HSL, CSS variables, a Tailwind configuration fragment, JSON, and SVG."],
  ["Can I save my palettes?", "Yes, up to 24 distinct palettes in this browser. Clearing browser data can remove them."],
  ["Can I use this with Tailwind CSS?", "Yes. Export the JavaScript theme configuration, or use the CSS variables in your styles."],
  ["Does this tool store my palettes online?", "No. Favorites stay in localStorage. Shared links contain the palette's color values."],
  ["How many colors are in each palette?", "Each palette contains five colors."]
];
