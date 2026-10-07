import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy | Color Palette Generator",
  description: "How Color Palette Generator handles your data: no account, browser-only generation, and local storage for saved palettes.",
  alternates: { canonical: "/privacy" },
};

/** Privacy policy page. */
export default function PrivacyPage() {
  return (
    <article className="mx-auto max-w-3xl space-y-4 px-4 py-12 leading-relaxed text-slate-700 sm:px-6">
      <h1 className="text-3xl font-bold text-slate-900">Privacy</h1>
      <ul className="list-disc space-y-2 pl-6">
        <li>No account is required, and the app does not ask you to submit personal information.</li>
        <li>Palette generation happens entirely in your browser.</li>
        <li>Saved palettes are stored in your browser&apos;s localStorage on this device. Clearing browser data may remove saved palettes.</li>
        <li>Shared palette URLs include the color values in the URL, so anyone with the link can see them.</li>
        <li>If palette naming is ever added, do not put sensitive information into palette names.</li>
        <li>No analytics are used today. If analytics are added later, they will be disclosed here before launch.</li>
      </ul>
    </article>
  );
}
