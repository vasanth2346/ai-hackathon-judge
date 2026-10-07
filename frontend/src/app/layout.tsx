import type { Metadata } from "next";
import "./globals.css";
import "./auth.css";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = { title: "Proof — Hackathon Judge", description: "Evidence-first judging for deployed hackathon projects." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppShell>{children}</AppShell></body></html>;
}
