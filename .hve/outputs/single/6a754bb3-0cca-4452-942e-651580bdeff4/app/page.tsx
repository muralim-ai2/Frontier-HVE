import PaletteGenerator from "@/components/PaletteGenerator";
import SeoContent from "@/components/SeoContent";
import { faqJsonLd, webApplicationJsonLd } from "@/lib/seo";

/** Home page with hero, generator, and educational content. */
export default function HomePage() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(webApplicationJsonLd()) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqJsonLd()) }} />
      <div className="mx-auto max-w-6xl px-4 pt-8 sm:px-6 sm:pt-12">
        <div className="mb-6 max-w-3xl">
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">Color Palette Generator</h1>
          <p className="mt-3 text-lg text-slate-600">
            Create beautiful, accessible color palettes for websites, brands, apps, and creative projects in seconds.
          </p>
          <p className="mt-2 text-sm text-slate-500">Runs in your browser. No signup required. Saved palettes stay on this device.</p>
        </div>
        <noscript>
          <p className="mb-4 rounded-lg bg-amber-50 p-3 text-amber-900">The palette generator needs JavaScript. The guides and FAQ below work without it.</p>
        </noscript>
        <PaletteGenerator />
      </div>
      <SeoContent />
    </>
  );
}
