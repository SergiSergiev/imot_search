import type { Metadata } from "next";
import Link from "next/link";
import { IconBuildingCommunity as BuildingCommunity, IconHeart as Heart, IconLayoutDashboard as LayoutDashboard, IconScale as Scale } from "@tabler/icons-react";
import "./globals.css";

export const metadata: Metadata = { title: "Brickwise — имотите, подредени", description: "Локален асистент за анализ на имоти" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="bg">
      <body>
        <header className="topbar">
          <Link href="/" className="brand"><span className="brand-mark"><BuildingCommunity size={21} /></span><span>brickwise</span></Link>
          <nav>
            <Link href="/"><LayoutDashboard size={18} /> Търсене</Link>
            <Link href="/agencies"><BuildingCommunity size={18} /> Агенции</Link>
            <Link href="/?favorites=1"><Heart size={18} /> Любими</Link>
            <Link href="/compare"><Scale size={18} /> Сравнение</Link>
          </nav>
          <div className="local-pill"><span /> Локален режим</div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
