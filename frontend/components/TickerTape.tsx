"use client";
import { useMemo } from "react";
import type { Quote } from "@/lib/types";
import { fmtPrice, fmtPct } from "@/lib/format";

// Ticker tape berjalan (marquee) — menampilkan emiten paling aktif (by volume).
const MAX_ITEMS = 60;

export default function TickerTape({ quotes }: { quotes: Quote[] }) {
  const items = useMemo(
    () =>
      quotes
        .filter((q) => q.price)
        .slice()
        .sort((a, b) => (b.volume || 0) - (a.volume || 0))
        .slice(0, MAX_ITEMS),
    [quotes]
  );

  if (!items.length) {
    return (
      <div className="h-8 border-t border-border bg-panel flex items-center px-3 text-[11px] text-dim">
        Memuat ticker…
      </div>
    );
  }

  const Row = ({ tag }: { tag: string }) => (
    <div className="flex items-center shrink-0">
      {items.map((q, i) => {
        const up = q.change_pct > 0, down = q.change_pct < 0;
        const cls = up ? "text-up" : down ? "text-down" : "text-dim";
        const arrow = up ? "↗" : down ? "↘" : "→";
        return (
          <span key={`${tag}-${q.symbol}-${i}`} className="flex items-center gap-1.5 px-4 text-xs whitespace-nowrap border-r border-border/40">
            <span className="font-semibold text-txt">{q.symbol}</span>
            <span className={cls}>{fmtPrice(q.price)}</span>
            <span className={`${cls} text-[11px]`}>{arrow} {fmtPct(q.change_pct)}</span>
          </span>
        );
      })}
    </div>
  );

  return (
    <div className="h-8 border-t border-border bg-panel overflow-hidden relative" title="Emiten paling aktif (by volume)">
      <div className="absolute inset-y-0 left-0 flex items-center marquee hover:[animation-play-state:paused]">
        <Row tag="a" />
        <Row tag="b" />
      </div>
    </div>
  );
}
