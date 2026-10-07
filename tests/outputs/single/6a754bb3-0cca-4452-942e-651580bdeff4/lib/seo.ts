/** Site-wide SEO constants and JSON-LD builders. */

/** Production origin; replace before deploying. */
export const SITE_URL = "https://colorpalettegenerator.example";
export const SITE_NAME = "Color Palette Generator";
export const SITE_TITLE = "Color Palette Generator | Create Beautiful Color Schemes";
export const SITE_DESCRIPTION =
  "Generate beautiful color palettes for websites, brands, apps, and creative projects. Copy HEX, RGB, HSL, CSS variables, Tailwind config, and more.";

export interface Faq {
  question: string;
  answer: string;
}

export const FAQS: Faq[] = [
  {
    question: "What is a color palette generator?",
    answer:
      "A color palette generator creates sets of colors that work well together. This tool builds five-color palettes from color harmony rules such as analogous, complementary, and triadic, or at random.",
  },
  {
    question: "Can I use these palettes for commercial projects?",
    answer:
      "Yes. Generated palettes are free to use in personal and commercial work. Colors are not exclusive, so other people may use the same combinations.",
  },
  {
    question: "Are the generated palettes accessible?",
    answer:
      "Each color shows contrast ratios against black and white and a simplified readability label. This is a helpful starting point, not a full accessibility audit, so test final designs in context.",
  },
  {
    question: "What color formats does this tool support?",
    answer: "You can copy HEX, RGB, and HSL values, and export the palette as CSS variables, a Tailwind config snippet, JSON, or an SVG swatch strip.",
  },
  {
    question: "Can I save my palettes?",
    answer: "Yes. Click Save palette to keep up to 24 recent palettes in your browser. You can reopen or delete them at any time.",
  },
  {
    question: "Can I use this with Tailwind CSS?",
    answer: "Yes. Open the Tailwind tab in the export panel and copy the theme.extend.colors snippet into your Tailwind configuration.",
  },
  {
    question: "Does this tool store my palettes online?",
    answer:
      "No. Saved palettes are stored in your browser's localStorage on this device only. Clearing browser data removes them. Shared links contain the color values in the URL.",
  },
  {
    question: "How many colors are in each palette?",
    answer: "Every palette has exactly five colors. Lock the ones you like and regenerate the rest.",
  },
];

/** Return WebApplication JSON-LD for the home page. */
export function webApplicationJsonLd(): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    name: SITE_NAME,
    url: SITE_URL,
    description: SITE_DESCRIPTION,
    applicationCategory: "DesignApplication",
    operatingSystem: "Any",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  };
}

/** Return FAQPage JSON-LD built from FAQS. */
export function faqJsonLd(): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQS.map((f) => ({ "@type": "Question", name: f.question, acceptedAnswer: { "@type": "Answer", text: f.answer } })),
  };
}
