import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://colorpalettegenerator.example"),
  title: "Color Palette Generator | Create Beautiful Color Schemes",
  description: "Generate beautiful color palettes for websites, brands, apps, and creative projects. Copy HEX, RGB, HSL, CSS variables, Tailwind config, and more.",
  alternates: { canonical: "/" },
  openGraph: { title: "Color Palette Generator", description: "Create beautiful color schemes in seconds.", images: ["/og-image.svg"] },
  twitter: { card: "summary_large_image", title: "Color Palette Generator", description: "Create beautiful color schemes in seconds.", images: ["/og-image.svg"] },
};

/** Render the application shell. */
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>): React.ReactElement {
  return <html lang="en"><body>{children}</body></html>;
}