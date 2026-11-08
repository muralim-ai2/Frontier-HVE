import Link from "next/link";

/** Top navigation bar with brand and section links. */
export default function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
      <nav aria-label="Main" className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 rounded-md font-semibold text-slate-900">
          <span aria-hidden="true" className="flex h-7 w-7 overflow-hidden rounded-lg">
            <span className="w-1/3 bg-[#264653]" />
            <span className="w-1/3 bg-[#E9C46A]" />
            <span className="w-1/3 bg-[#E76F51]" />
          </span>
          Color Palette Generator
        </Link>
        <ul className="hidden gap-5 text-sm text-slate-700 sm:flex">
          <li><Link href="/#export" className="rounded hover:text-slate-950">Export</Link></li>
          <li><Link href="/#saved" className="rounded hover:text-slate-950">Saved</Link></li>
          <li><Link href="/#faq" className="rounded hover:text-slate-950">FAQ</Link></li>
        </ul>
      </nav>
    </header>
  );
}
