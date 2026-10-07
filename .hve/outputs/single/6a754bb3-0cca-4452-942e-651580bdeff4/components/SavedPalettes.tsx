"use client";

import type { SavedPalette } from "@/lib/storage";

interface SavedPalettesProps {
  palettes: SavedPalette[];
  storageMessage: string | null;
  onLoad: (colors: string[]) => void;
  onDelete: (id: string) => void;
}

/** Grid of saved palettes with load and delete actions. */
export default function SavedPalettes({ palettes, storageMessage, onLoad, onDelete }: SavedPalettesProps) {
  return (
    <section id="saved" aria-labelledby="saved-heading" className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      <h2 id="saved-heading" className="text-xl font-semibold">Saved palettes</h2>
      {storageMessage && <p role="status" className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{storageMessage}</p>}
      {palettes.length === 0 ? (
        <p className="mt-3 text-slate-600">No saved palettes yet. Save your favorite combinations here.</p>
      ) : (
        <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {palettes.map((p) => (
            <li key={p.id} className="flex items-center gap-2 rounded-xl border border-slate-200 p-2">
              <button
                type="button"
                onClick={() => onLoad(p.colors)}
                aria-label={`Load palette ${p.colors.map((c) => `#${c}`).join(", ")}`}
                className="flex h-12 flex-1 overflow-hidden rounded-lg"
              >
                {p.colors.map((c, i) => (
                  <span key={i} className="flex-1" style={{ backgroundColor: `#${c}` }} />
                ))}
              </button>
              <button
                type="button"
                onClick={() => onDelete(p.id)}
                aria-label={`Delete palette ${p.colors.map((c) => `#${c}`).join(", ")}`}
                className="rounded-lg px-2 py-1.5 text-sm text-slate-600 hover:bg-red-50 hover:text-red-700"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
