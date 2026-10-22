import type { Metadata } from "next";
import { Listener } from "@/components/heardit";
export const metadata: Metadata = { title: "Listening test", robots: { index: false, follow: false } };
export default async function Page({params}:{params:Promise<{id:string}>}){const {id}=await params;return <Listener id={id}/>}
