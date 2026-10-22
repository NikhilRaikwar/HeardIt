"use client";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { MotionConfig } from "motion/react";
export function Providers({ children }: { children: React.ReactNode }) { return <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange><MotionConfig reducedMotion="user"><TooltipProvider>{children}</TooltipProvider></MotionConfig><Toaster position="bottom-right" richColors closeButton /></ThemeProvider>; }
