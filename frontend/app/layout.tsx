import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Serif } from "next/font/google";
import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexSerif = IBM_Plex_Serif({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "600", "700"],
  variable: "--font-plex-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "VeriSonar",
  description: "Plataforma de análisis de voz y auditoría VSA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${plexSans.variable} ${plexSerif.variable}`}>
      <body className={plexSans.className}>{children}</body>
    </html>
  );
}
