import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Harmonix — CPSE Material Harmonization",
  description:
    "Neutral National Material Identifier layer and legacy-code crosswalk for Central Public Sector Enterprises.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
