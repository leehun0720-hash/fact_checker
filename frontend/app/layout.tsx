import type { Metadata } from "next";
import AppFrame from "@/components/AppFrame";
import "./globals.css";

export const metadata: Metadata = {
  title: "문서 검증 — TEN AI Doc Fact Checker",
  description: "AI 초안 문서의 수치·출처·법령·내부 정합성을 검증합니다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <AppFrame>{children}</AppFrame>
      </body>
    </html>
  );
}
