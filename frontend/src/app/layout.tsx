import type { Metadata } from "next";
import { Fira_Code, Inter } from "next/font/google";
import "./globals.css";
import AnalyticsConsent from "@/components/AnalyticsConsent";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const firaCode = Fira_Code({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ARGO | Executive Command Suite",
  description: "Decision intelligence and retention engine.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body
        className={`${inter.variable} ${firaCode.variable} flex min-h-full flex-col`}
      >
        {children}
        <AnalyticsConsent />
      </body>
    </html>
  );
}
