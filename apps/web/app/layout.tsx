import "./globals.css";
import type { Metadata } from "next";
import { Poppins } from "next/font/google";

// Poppins est aussi la police du CV W hub généré : l'outil et le document parlent la même langue.
const poppins = Poppins({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-poppins",
});

export const metadata: Metadata = {
  title: { default: "CV Factory", template: "%s · CV Factory" },
  description: "Outil interne W hub : mise au format et relecture des CV candidats.",
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className={poppins.variable}>{children}</body>
    </html>
  );
}
