import type { Metadata } from "next";
import type { ReactNode, ReactElement } from "react";
import Link from "next/link";
import { description, siteUrl, title } from "../lib/seo";
import "./globals.css";
export const metadata: Metadata = { metadataBase: new URL(siteUrl), title, description, alternates: { canonical: "/" }, openGraph: { title, description, url: "/", type: "website", images: [{ url: "/og-image.svg", width: 1200, height: 630, alt: "Color Palette Generator: five color swatches" }] }, twitter: { card: "summary_large_image", title, description, images: ["/og-image.svg"] }, icons: { icon: "/og-image.svg" } };
/** Render the shared accessible page shell. */
export default function RootLayout({ children }: { children: ReactNode }): ReactElement { return <html lang="en"><body><a className="skip" href="#main">Skip to content</a><header><Link className="brand" href="/"><span className="brand-mark" aria-hidden="true" />Color Palette Generator</Link><span className="eyebrow">A little color. A lot of possibility.</span></header><main id="main">{children}</main><footer><p>Runs in your browser. No signup required. Saved palettes stay on this device.</p><nav aria-label="Legal"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></nav></footer></body></html>; }
