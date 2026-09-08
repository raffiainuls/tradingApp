"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AiPick, AiPickBatch, AiPicksHistoryResponse } from "@/lib/types";
import { fmtPct, fmtPrice } from "@/lib/format";

type PickStatus = "Hit TP1" | "Hit TP2" | "Hit TP3" | "Cut Loss" | "Still Open";

function normalizeBatches(data: AiPicksHistoryResponse): AiPickBatch[] {
  if (Array.isArray(data.batches)) return data.batches;
  const grouped = new Map<string, AiPick[]>();
  for (const pick of data.picks ?? []) {
    const key = pick.batch_at;
    grouped.set(key, [...(grouped.get(key) ?? []), pick]);
  }
  return [...grouped.entries()].map(([batch_at, picks]) => ({ batch_at, picks }));
}

function statusOf(pick: AiPick): PickStatus {
  const supplied = pick.status?.toUpperCase().replaceAll("_", " ");
  if (supplied === "HIT TP3") return "Hit TP3";
  if (supplied === "HIT TP2") return "Hit TP2";
  if (supplied === "HIT TP1" || supplied === "HIT TARGET") return "Hit TP1";
  if (supplied === "CUT LOSS") return "Cut Loss";
  if (supplied === "STILL OPEN") return "Still Open";
  // Backend status is authoritative. This aggregate-based fallback deliberately
  // avoids inferring historical triggers from the latest price.
  if (pick.min_low != null && pick.min_low <= pick.cutloss_price) return "Cut Loss";
  if (pick.max_high != null && pick.tp3 != null && pick.max_high >= pick.tp3) return "Hit TP3";
  if (pick.max_high != null && pick.tp2 != null && pick.max_high >= pick.tp2) return "Hit TP2";
  if (pick.max_high != null && pick.max_high >= (pick.tp1 ?? pick.target_price)) return "Hit TP1";
  return "Still Open";
}

function pnlOf(pick: AiPick, status: PickStatus): number | null {
  if (pick.pnl_pct != null) return pick.pnl_pct;
  if (!pick.entry_price) return null;
  if (status === "Cut Loss") return ((pick.cutloss_price - pick.entry_price) / pick.entry_price) * 100;
  if (status.startsWith("Hit TP") && pick.max_high != null) return ((pick.max_high - pick.entry_price) / pick.entry_price) * 100;
  const currentClose = pick.current_close ?? pick.current_price;
  return currentClose == null ? null : ((currentClose - pick.entry_price) / pick.entry_price) * 100;
}

function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("id-ID", {
    dateStyle: "full", timeStyle: "short",
  }).format(date);
}

export default function AiPicksHistoryPage() {
  const [batches, setBatches] = useState<AiPickBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setBatches(normalizeBatches(await api.aiPicksHistory())); }
    catch { setError("Riwayat AI Picks belum dapat dimuat. Pastikan layanan backend aktif lalu coba lagi."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const sorted = useMemo(() => [...batches].sort((a, b) => Date.parse(b.batch_at) - Date.parse(a.batch_at)), [batches]);

  return <div className="h-full overflow-y-auto">
    <header className="page-header flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-xl font-bold">Riwayat AI Picks</h1>
      <p className="mt-0.5 text-xs text-dim">Pantau hasil rekomendasi dari setiap batch berdasarkan harga pasar terkini.</p></div>
      <Link href="/watchlist" className="btn">← Kembali ke Watchlist</Link>
    </header>
    <main className="page-content space-y-5" aria-busy={loading} aria-live="polite">
      {loading && <div className="status-message">Memuat riwayat AI Picks…</div>}
      {error && <div className="status-message border-down/40 text-down" role="alert"><p>{error}</p><button className="btn mt-3" onClick={load}>Coba lagi</button></div>}
      {!loading && !error && !sorted.length && <div className="status-message">Belum ada riwayat. Generate AI Picks pertama Anda dari halaman Watchlist.</div>}
      {sorted.map((batch) => <section key={batch.batch_at} aria-labelledby={`batch-${batch.batch_at}`}>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 id={`batch-${batch.batch_at}`} className="text-sm font-semibold">{dateLabel(batch.batch_at)}</h2>
          <span className="chip">{batch.picks.length} rekomendasi</span>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {batch.picks.map((pick) => <PickCard key={pick.id} pick={pick} />)}
        </div>
      </section>)}
    </main>
  </div>;
}

function PickCard({ pick }: { pick: AiPick }) {
  const status = statusOf(pick); const pnl = pnlOf(pick, status);
  const isTarget = status.startsWith("Hit TP");
  const tone = isTarget ? "text-up border-up/40 bg-up/10" : status === "Cut Loss" ? "text-down border-down/40 bg-down/10" : "text-dim border-border bg-panel2";
  const pnlLabel = isTarget ? "Max Profit Reached" : status === "Cut Loss" ? "Cutloss Triggered" : "Unrealized P/L";
  const currentClose = pick.current_close ?? pick.current_price;
  const levels = [
    ["Buy Area", pick.buy_area_low != null && pick.buy_area_high != null ? `${fmtPrice(pick.buy_area_low)}–${fmtPrice(pick.buy_area_high)}` : fmtPrice(pick.entry_price)],
    ["TP1", fmtPrice(pick.tp1 ?? pick.target_price)], ["TP2", pick.tp2 != null ? fmtPrice(pick.tp2) : "–"], ["TP3", pick.tp3 != null ? fmtPrice(pick.tp3) : "–"],
    ["Cutloss", pick.cutloss_area_low != null && pick.cutloss_area_high != null ? `${fmtPrice(pick.cutloss_area_low)}–${fmtPrice(pick.cutloss_area_high)}` : fmtPrice(pick.cutloss_price)],
  ];
  return <article className="card overflow-hidden">
    <div className="flex items-start justify-between gap-3 p-4">
      <div><Link href={`/analyst?symbol=${pick.symbol}`} className="font-bold hover:text-accent">{pick.symbol}</Link><p className="mt-0.5 text-[11px] text-dim">Entry {fmtPrice(pick.entry_price)} · Kini {currentClose != null ? fmtPrice(currentClose) : "–"}</p></div>
      <div className="text-right"><span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-semibold ${tone}`}>{status}</span><p className={`mt-1 font-mono text-sm font-bold ${pnl == null ? "text-dim" : status === "Still Open" ? (pnl >= 0 ? "text-dim" : "text-warn") : pnl >= 0 ? "text-up" : "text-down"}`}>{pnl == null ? "P&L –" : fmtPct(pnl)}</p><p className="mt-0.5 text-[9px] text-dim">{pnlLabel}</p></div>
    </div>
    <dl className="grid grid-cols-2 gap-px border-t border-border bg-border sm:grid-cols-5">
      {levels.map(([label, value]) => <div key={label} className="bg-panel px-2 py-2"><dt className="text-[9px] uppercase tracking-wide text-dim">{label}</dt><dd className="mt-0.5 whitespace-nowrap font-mono text-[11px]">{value}</dd></div>)}
    </dl>
  </article>;
}
