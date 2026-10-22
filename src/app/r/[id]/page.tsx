import type { Metadata } from "next";
import { Results } from "@/components/heardit";
export const metadata: Metadata = { title: "Private test results", robots: { index: false, follow: false } };
export default async function Page({params}:{params:Promise<{id:string}>}){const {id}=await params;return <Results id={id}/>}
