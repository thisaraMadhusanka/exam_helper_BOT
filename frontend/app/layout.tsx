import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ruixen AI",
  description: "Intelligent PDF Knowledge Assistant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full dark" suppressHydrationWarning>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="h-full bg-[#07080E] text-white antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
