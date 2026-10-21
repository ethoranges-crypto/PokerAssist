import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "PokerAssist", description: "No-Limit Hold'em decision assistant" };
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
