import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-6 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">404</h1>
      <p className="mt-2 text-sm text-muted-foreground">This page could not be found.</p>
      <Button asChild variant="outline" className="mt-6 gap-2">
        <Link href="/">
          <ArrowLeft size={14} /> Back to home
        </Link>
      </Button>
    </main>
  );
}
