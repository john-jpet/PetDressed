import type { Metadata } from "next";
import { Geist, Fraunces } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
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
        className={`${geistSans.variable} ${fraunces.variable}`}
      >
        {children}
      </body>
    </html>
  );
}
