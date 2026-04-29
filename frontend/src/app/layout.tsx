import type { Metadata } from "next";
import "./globals.css";
import Providers from "@/components/providers";

export const metadata: Metadata = {
  title: "MedTruth AI — Evidence-Grounded Medical Q&A",
  description:
    "AI-powered medical question answering backed exclusively by PubMed, BMJ, The Lancet, Nature Medicine, WHO, and Cochrane Reviews.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-slate-900 transition-colors dark:bg-[#0b1220] dark:text-slate-100">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
