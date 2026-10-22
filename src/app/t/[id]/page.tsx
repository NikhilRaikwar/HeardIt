import type { Metadata } from "next";
import { Listener } from "@/components/heardit";

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: "A HeardIt listening experiment",
    description: "Listen or read the same words, then choose the interpretation that fits best.",
    robots: { index: false, follow: false },
    openGraph: {
      title: "A HeardIt listening experiment",
      description: "Listen or read the same words, then choose the interpretation that fits best.",
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: "A HeardIt listening experiment",
      description: "Listen or read the same words, then choose the interpretation that fits best.",
    },
  };
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Listener id={id} />;
}
