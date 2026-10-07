import Link from "next/link";

/** Site footer with legal links, trust copy, and Pro note. */
export default function Footer() {
  return (
    <footer className="mt-16 border-t border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>Runs in your browser. No signup required. Saved palettes stay on this device.</p>
        <p className="text-slate-500">Coming soon: Pro exports and brand kits.</p>
        <ul className="flex gap-4">
          <li><Link href="/privacy" className="rounded underline-offset-4 hover:underline">Privacy</Link></li>
          <li><Link href="/terms" className="rounded underline-offset-4 hover:underline">Terms</Link></li>
        </ul>
      </div>
    </footer>
  );
}
