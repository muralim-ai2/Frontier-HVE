import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms | Color Palette Generator",
  description: "Terms of use for Color Palette Generator.",
  alternates: { canonical: "/terms" },
};

/** Terms of use page. */
export default function TermsPage() {
  return (
    <article className="mx-auto max-w-3xl space-y-4 px-4 py-12 leading-relaxed text-slate-700 sm:px-6">
      <h1 className="text-3xl font-bold text-slate-900">Terms</h1>
      <ul className="list-disc space-y-2 pl-6">
        <li>This tool is provided for general creative and design use, free of charge and as is.</li>
        <li>There is no guarantee that generated palettes are suitable for every brand, accessibility requirement, or legal use case.</li>
        <li>You are responsible for testing colors in your own context.</li>
        <li>Generated palettes are not exclusive intellectual property and are not guaranteed to be unique.</li>
        <li>Generated palettes are not legal brand advice.</li>
        <li>Accessibility labels are simplified and should be verified in real layouts.</li>
      </ul>
    </article>
  );
}
