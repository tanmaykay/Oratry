import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Oratry — Speak with intent", description: "Deliberate speaking practice." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
