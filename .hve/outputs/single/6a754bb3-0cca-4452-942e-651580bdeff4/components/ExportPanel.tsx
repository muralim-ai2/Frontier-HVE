"use client";

import { useState } from "react";
import CopyButton from "./CopyButton";
import { paletteToCssVariables, paletteToJson, paletteToSvg, paletteToTailwindConfig } from "@/lib/export";
import type { Palette } from "@/lib/palette";

const FORMATS = {
  CSS: paletteToCssVariables,
  Tailwind: paletteToTailwindConfig,
  JSON: paletteToJson,
  SVG: paletteToSvg,
} as const;

type Format = keyof typeof FORMATS;

/** Tabbed export panel with copy and SVG download. */
export default function ExportPanel({ palette }: { palette: Palette }) {
  const [format, setFormat] = useState<Format>("CSS");
  const output = FORMATS[format](palette);

  function downloadSvg(): void {
    const url = URL.createObjectURL(new Blob([paletteToSvg(palette)], { type: "image/svg+xml" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `palette-${palette.join("-")}.svg`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section id="export" aria-labelledby="export-heading" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="export-heading" className="text-xl font-semibold">Export your palette</h2>
        <div role="group" aria-label="Export format" className="flex flex-wrap gap-1 rounded-xl bg-slate-100 p-1">
          {(Object.keys(FORMATS) as Format[]).map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={format === f}
              onClick={() => setFormat(f)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium ${format === f ? "bg-white text-slate-900 shadow-sm" : "text-slate-700 hover:text-slate-900"}`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
      <pre className="mt-4 max-h-72 overflow-auto rounded-xl bg-slate-900 p-4 text-sm text-slate-100">
        <code>{output}</code>
      </pre>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <CopyButton text={output} label={`Copy ${format} export`} className="bg-slate-900 px-4 py-2 text-white hover:bg-slate-700">
          {`Copy ${format}`}
        </CopyButton>
        {format === "SVG" && (
          <button type="button" onClick={downloadSvg} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50">
            Download SVG
          </button>
        )}
        <p className="ml-auto text-xs text-slate-500">Coming soon: Pro exports and brand kits.</p>
      </div>
    </section>
  );
}
