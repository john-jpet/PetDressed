import type { Metadata } from "next";
import { Archivo_Black, Space_Mono } from "next/font/google";
import "./globals.css";

const display = Archivo_Black({
  variable: "--font-display",
  weight: "400",
  subsets: ["latin"],
});

const mono = Space_Mono({
  variable: "--font-mono",
  weight: ["400", "700"],
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PetDressed — Your wardrobe, thoughtfully planned",
  description:
    "Digitize your wardrobe and plan practical, weather-aware outfits.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  openGraph: {
    title: "PetDressed — Your wardrobe, thoughtfully planned",
    description: "Dress for the day. Love what you own.",
    type: "website",
    images: [{ url: "/petdressed-social.png", width: 1733, height: 907 }],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/petdressed-social.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${display.variable} ${mono.variable}`}
      >
        {children}
      </body>
    </html>
  );
}
