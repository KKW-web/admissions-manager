import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "2027 수시진학관리",
  description: "관리자 입력과 담당 반 조회를 위한 비공개 수시진학관리",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body style={{margin:0}}>{children}</body>
    </html>
  );
}
