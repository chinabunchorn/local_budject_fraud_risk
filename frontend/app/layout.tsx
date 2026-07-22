import type { Metadata } from "next";
import { Sarabun } from "next/font/google";
import "./globals.css";

import { Providers } from "./providers";

const sarabun = Sarabun({
  variable: "--font-sans",
  subsets: ["thai", "latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "ระบบช่วยวิเคราะห์ความเสี่ยงงบประมาณท้องถิ่น",
  description:
    "แดชบอร์ดสนับสนุนผู้ตรวจสอบ: แจ้งจุดที่ควรตรวจสอบเพิ่มเติม ผู้ตรวจสอบเป็นผู้ตัดสินใจขั้นสุดท้าย",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="th" className={`${sarabun.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
