import "./globals.css";
import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "IDX Trading App",
  description: "Personal stock trading app — Journal & Technical Analyst",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>
        <div className="flex h-dvh overflow-hidden">
          <Sidebar />
          <main id="main-content" className="min-w-0 flex-1 overflow-hidden pb-16 md:pb-0">{children}</main>
        </div>
      </body>
    </html>
  );
}
