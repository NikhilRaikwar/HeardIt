import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";
const configuredAppUrl = process.env.NEXT_PUBLIC_APP_URL?.trim();
if (process.env.NODE_ENV === "production" && !configuredAppUrl) {
  throw new Error("NEXT_PUBLIC_APP_URL must be set to the public HTTPS HeardIt origin for production metadata and share links.");
}
const appUrl = configuredAppUrl || "http://localhost:3000";
if (process.env.NODE_ENV === "production" && !appUrl.startsWith("https://")) {
  throw new Error("NEXT_PUBLIC_APP_URL must use HTTPS in production.");
}
const socialImage = {
  url: "/banner.png",
  width: 1731,
  height: 909,
  alt: "HeardIt — Same words, four meanings. A listening experiment for AI voices.",
};
const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });
const serif = Instrument_Serif({ subsets: ["latin"], variable: "--font-instrument-serif", weight: "400", style: ["normal", "italic"], display: "swap" });
export const metadata: Metadata = {
  metadataBase: new URL(appUrl),
  title: { default: "HeardIt — Same words. Four meanings.", template: "%s · HeardIt" },
  description: "Can you hear what an AI voice really means? Create a listening test and measure what people hear.",
  applicationName: "HeardIt",
  keywords: ["AI voice", "listening experiment", "voice interpretation", "Fish Audio", "A/B test", "speech perception"],
  alternates: { canonical: "/" },
  robots: { index: true, follow: true, googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1, "max-video-preview": -1 } },
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/icon", type: "image/png", sizes: "32x32" },
    ],
    apple: [{ url: "/apple-icon", sizes: "180x180", type: "image/png" }],
  },
  openGraph: {
    type: "website",
    siteName: "HeardIt",
    url: "/",
    title: "HeardIt — Same words. Four meanings.",
    description: "Can you hear what an AI voice really means? Create a listening test and see what people hear.",
    images: [socialImage],
  },
  twitter: {
    card: "summary_large_image",
    title: "HeardIt — Same words. Four meanings.",
    description: "One sentence. Four possible interpretations. What will listeners hear?",
    images: [socialImage],
  },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
 return <html lang="en" suppressHydrationWarning><body className={`${geist.variable} ${mono.variable} ${serif.variable}`}><Providers>{children}</Providers></body></html>;
}
