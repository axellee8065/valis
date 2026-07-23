import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Valis Protocol — 온체인 부동산 감정 인프라",
  description:
    "실거래·정부 데이터·AI AVM을 결합해 부동산 가치를 검증 가능한 형태로 온체인에 게시하는 프로토콜. 모든 RWA 부동산 프로토콜의 신뢰 레이어.",
  openGraph: {
    title: "Valis Protocol",
    description:
      "온체인 부동산 감정 인프라 — 서울 아파트 35만 실거래를 학습한 AVM이 신뢰구간과 함께 Sui에 attestation을 발행합니다.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
