import type { Metadata } from "next";
import { CreatorJourney } from "@/components/creator-journey";
export const metadata: Metadata = { title: "Create a listening test", robots: { index: false, follow: false } };
export default function Page(){return <CreatorJourney/>}
