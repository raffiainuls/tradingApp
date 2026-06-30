"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/journal", label: "Trading Journal", icon: "📓", n: 1, ready: true },
  { href: "/analyst", label: "Trading Analyst", icon: "📈", n: 2, ready: true },
  { href: "/watchlist", label: "Watchlist", icon: "⭐", n: 3, ready: true },
  { href: "/screener", label: "Screener", icon: "🔎", n: 4, ready: false },
  { href: "/advisor", label: "AI Advisor", icon: "🤖", n: 5, ready: false },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="w-60 shrink-0 bg-panel border-r border-border flex flex-col">
      <div className="px-5 py-4 border-b border-border">
        <div className="text-lg font-bold tracking-tight">
          IDX<span className="text-accent">Trader</span>
        </div>
        <div className="text-[11px] text-dim mt-0.5">Personal Trading Suite</div>
      </div>

      <nav className="flex-1 py-3">
        {NAV.map((item) => {
          const active = path.startsWith(item.href);
          const base =
            "flex items-center gap-3 mx-2 px-3 py-2.5 rounded-md text-sm transition-colors";
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
              className={`${base} ${
                active ? "bg-accent/15 text-accent" : "text-dim hover:text-txt hover:bg-panel2"
              }`}
            >
              <span className="text-base">{item.icon}</span>
              <span className="flex-1">{item.label}</span>
              <span className="text-[10px] text-dim">{item.n}</span>
            </Link>
          );
        })}
      </nav>

      <div className="px-5 py-3 border-t border-border text-[10px] text-dim">
        Data: yFinance (delay 15m)
        <br />
        Kafka · ClickHouse · Postgres
      </div>
    </aside>
  );
}
