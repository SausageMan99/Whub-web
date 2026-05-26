import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "W hub CV Factory",
  description: "Portail interne de génération de CV W hub"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
