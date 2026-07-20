import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DocuGuardian — Document intelligence, before the risk",
  description: "AI-powered document intelligence for the decisions that matter."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
