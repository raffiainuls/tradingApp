"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/journal", label: "Trading Journal", icon: "📓", n: 1, ready: true },
  { href: "/analyst", label: "Trading Analyst", icon: "📈", n: 2, ready: true },
  { href: "/watchlist", label: "Watchlist", icon: "⭐", n: 3, ready: true },
  { href: "/screener", label: "Screener", icon: "🔎", n: 4, ready: true },
  { href: "/advisor", label: "AI Advisor", icon: "🤖", n: 5, ready: true },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="fixed inset-x-0 bottom-0 z-50 h-16 border-t border-border bg-panel md:static md:h-auto md:w-60 md:shrink-0 md:border-r md:border-t-0 flex md:flex-col" aria-label="Navigasi utama">
      <div className="hidden px-5 py-4 border-b border-border md:block">
        <div className="text-lg font-bold tracking-tight">
          IDX<span className="text-accent">Trader</span>
        </div>
        <div className="text-[11px] text-dim mt-0.5">Personal Trading Suite</div>
      </div>

      <nav className="flex flex-1 items-stretch justify-around md:block md:py-3">
        {NAV.map((item) => {
          const active = path.startsWith(item.href);
          const base =
            "flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 px-1 py-2 text-[10px] transition-colors md:mx-2 md:flex-row md:justify-start md:gap-3 md:rounded-md md:px-3 md:py-2.5 md:text-sm";
          if (!item.ready) {
            return (
              <div
                key={item.href}
                className={`${base} text-dim/50 cursor-not-allowed`}
                title="Segera hadir"
              >
                <span className="text-base opacity-60">{item.icon}</span>
                <span className="flex-1">{item.label}</span>
                <span className="chip">soon</span>
              </div>
            );
          }
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={`${base} ${
                active ? "bg-accent/15 text-accent" : "text-dim hover:text-txt hover:bg-panel2"
              }`}
            >
              <span className="text-base" aria-hidden="true">{item.icon}</span>
              <span className="max-w-full truncate md:flex-1">{item.label.replace("Trading ", "")}</span>
              <span className="hidden text-[10px] text-dim md:inline">{item.n}</span>
            </Link>
          );
        })}
      </nav>

      <div className="hidden px-5 py-3 border-t border-border text-[10px] text-dim md:block">
        Data: yFinance (delay 15m)
        <br />
        Kafka · ClickHouse · Postgres
      </div>
    </aside>
  );
}
