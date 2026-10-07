"use client";

import CopyButton from "./CopyButton";
import { formatHsl, formatRgb, getBestTextColor, getContrastLabel, getContrastRatio } from "@/lib/color";

interface ColorCardProps {
  hex: string;
  index: number;
  locked: boolean;
  onToggleLock: (index: number) => void;
}

/** Large swatch card showing color values, copy buttons, lock toggle, and contrast guidance. */
export default function ColorCard({ hex, index, locked, onToggleLock }: ColorCardProps) {
  const text = getBestTextColor(hex);
  const vsBlack = getContrastRatio(hex, "000000");
  const vsWhite = getContrastRatio(hex, "FFFFFF");
  const label = getContrastLabel(Math.max(vsBlack, vsWhite));
  const onSwatch = text === "black" ? "text-black hover:bg-black/10" : "text-white hover:bg-white/15";

  return (
    <li className="flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex min-h-40 flex-col justify-between p-3 sm:min-h-56" style={{ backgroundColor: `#${hex}` }}>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => onToggleLock(index)}
            aria-pressed={locked}
            aria-label={`${locked ? "Unlock" : "Lock"} color ${index + 1}, #${hex}`}
            className={`rounded-lg px-2.5 py-1.5 text-sm font-semibold ${onSwatch} ${locked ? "ring-2 ring-current" : ""}`}
          >
            <span aria-hidden="true">{locked ? "🔒 " : "🔓 "}</span>
            {locked ? "Locked" : "Lock"}
          </button>
        </div>
        <CopyButton text={`#${hex}`} label={`Copy HEX #${hex}`} className={`self-start font-mono text-lg font-bold ${onSwatch}`}>
          {`#${hex}`}
        </CopyButton>
      </div>
      <dl className="space-y-1.5 p-3 text-sm">
        {[
          ["RGB", formatRgb(hex)],
          ["HSL", formatHsl(hex)],
        ].map(([name, value]) => (
          <div key={name} className="flex items-center justify-between gap-2">
            <dt className="text-slate-500">{name}</dt>
            <dd>
              <CopyButton text={value} label={`Copy ${name} ${value}`} className="font-mono text-xs text-slate-800 hover:bg-slate-100">
                {value}
              </CopyButton>
            </dd>
          </div>
        ))}
        <div className="flex justify-between gap-2 border-t border-slate-100 pt-2">
          <dt className="text-slate-500">Best text</dt>
          <dd className="font-medium capitalize">{text}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">vs black / white</dt>
          <dd className="font-mono text-xs">
            {vsBlack.toFixed(2)} / {vsWhite.toFixed(2)}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-500">Contrast</dt>
          <dd className="font-medium">
            <span aria-hidden="true">{label === "Good for text" ? "✓ " : label === "Use carefully" ? "! " : "✕ "}</span>
            {label}
          </dd>
        </div>
      </dl>
    </li>
  );
}
