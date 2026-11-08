import { FAQS } from "@/lib/seo";

/** Educational content and FAQ shown below the generator. */
export default function SeoContent() {
  return (
    <div className="mx-auto mt-16 max-w-3xl space-y-12 px-4 text-slate-700 sm:px-6">
      <section aria-labelledby="how-heading">
        <h2 id="how-heading" className="text-2xl font-semibold text-slate-900">How to use this color palette generator</h2>
        <ol className="mt-4 list-decimal space-y-1.5 pl-6">
          <li>Start with a random palette or enter a seed color.</li>
          <li>Choose a harmony mode.</li>
          <li>Lock colors you like.</li>
          <li>Regenerate the rest.</li>
          <li>Copy HEX, RGB, HSL, CSS, or Tailwind values.</li>
          <li>Save or share your palette.</li>
        </ol>
      </section>
      <section aria-labelledby="why-heading">
        <h2 id="why-heading" className="text-2xl font-semibold text-slate-900">Why color palettes matter</h2>
        <p className="mt-4 leading-relaxed">
          A consistent set of colors makes a website, brand, or app feel recognizable and polished. When buttons, headings, and backgrounds draw
          from the same palette, people learn what each color means faster, and the interface becomes easier to scan and use.
        </p>
      </section>
      <section aria-labelledby="tips-heading">
        <h2 id="tips-heading" className="text-2xl font-semibold text-slate-900">Tips for choosing accessible colors</h2>
        <ul className="mt-4 list-disc space-y-1.5 pl-6">
          <li>Test text against every background it will appear on.</li>
          <li>Use high contrast for body text; WCAG AA asks for at least 4.5:1.</li>
          <li>Reserve low-contrast colors for decoration, borders, and large shapes.</li>
          <li>Check colors in the actual design context, not just as swatches.</li>
          <li>This tool gives guidance, but you should still test final designs.</li>
        </ul>
      </section>
      <section id="faq" aria-labelledby="faq-heading">
        <h2 id="faq-heading" className="text-2xl font-semibold text-slate-900">Frequently asked questions</h2>
        <div className="mt-4 divide-y divide-slate-200 rounded-2xl border border-slate-200 bg-white">
          {FAQS.map((f) => (
            <details key={f.question} className="group p-4">
              <summary className="cursor-pointer rounded font-medium text-slate-900">{f.question}</summary>
              <p className="mt-2 leading-relaxed">{f.answer}</p>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
