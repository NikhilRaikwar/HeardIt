import type { Metadata } from "next";
import { CreatedPage } from "@/components/creator-journey";

export const metadata: Metadata = { title: "Test published", robots: { index: false, follow: false } };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CreatedPage id={id} />;
}
