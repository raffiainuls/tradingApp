"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AiPick, AiPicksStatus, WatchlistItem } from "@/lib/types";
import { fmtPrice, scoreColor } from "@/lib/format";
import VerdictBadge from "@/components/VerdictBadge";

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 1) return "baru saja";
  if (mins < 60) return `${mins} menit lalu`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h} jam lalu`;
  return `${Math.round(h / 24)} hari lalu`;
}

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [addSym, setAddSym] = useState("");
  const [addNote, setAddNote] = useState("");

  const [aiPicks, setAiPicks] = useState<AiPick[]>([]);
  const [aiStatus, setAiStatus] = useState<AiPicksStatus | null>(null);
  const prevGen = useRef(false);

  const loadWatch = () => api.watchlist().then((d) => setItems(d.watchlist)).catch(() => {});
  const loadAiPicks = () => api.aiPicks().then((d) => setAiPicks(d.picks)).catch(() => {});

  const add = async (sym: string, note?: string) => {
    if (!sym) return;
    try { await api.addWatchlist({ symbol: sym.toUpperCase(), note }); setAddSym(""); setAddNote(""); loadWatch(); }
    catch {}
  };
  const remove = async (id: number) => { await api.delWatchlist(id); loadWatch(); };

  const refresh = async () => {
    try {
      await api.generateAiPicks();
      // optimis: mulai polling walau BackgroundTasks baru jalan setelah response
      setAiStatus((s) => ({ generating: true, last_generated_at: s?.last_generated_at ?? null }));
    } catch {}
  };

  // ── Mount: load batch yang ADA (read-only, TIDAK memicu generate) ──
  // Cek status sekali supaya kalau tab/user lain sedang generate, tab ini ikut polling & update.
  useEffect(() => {
    loadWatch();
    loadAiPicks();
    api.aiPicksStatus().then((s) => setAiStatus(s)).catch(() => {});
  }, []);

  // ── Polling status tiap 4 detik SELAMA generating ──
  useEffect(() => {
    if (!aiStatus?.generating) return;
    const id = window.setInterval(() => {
      api.aiPicksStatus().then((s) => setAiStatus(s)).catch(() => {});
    }, 4000);
    return () => window.clearInterval(id);
  }, [aiStatus?.generating]);

  // ── Saat generating selesai (true → false): reload picks ──
  useEffect(() => {
    const gen = !!aiStatus?.generating;
    if (prevGen.current && !gen) {
      loadAiPicks();
      loadWatch();
    }
    prevGen.current = gen;
  }, [aiStatus?.generating]);

  const watchSet = useMemo(() => new Set(items.map((i) => i.symbol)), [items]);
  const generating = !!aiStatus?.generating;
  const lastBatchAt = aiPicks[0]?.batch_at ?? null;

  return (
    <div className="h-full overflow-y-auto">
      <div className="page-header flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-xl font-bold">Watchlist</h1>
        <p className="text-xs text-dim mt-0.5">Saham pantauan manual + AI Picks harian (top bullish dari seluruh universe IDX)</p></div>
        <Link href="/watchlist/history" className="btn" aria-label="Buka riwayat AI Picks">Riwayat AI Picks →</Link>
      </div>

      <div className="page-content grid lg:grid-cols-[300px_1fr] gap-4">
        {/* ── Watchlist manual ── */}
        <div className="space-y-3">
          <div className="card p-3">
            <div className="label mb-2">Tambah ke Watchlist</div>
            <div className="space-y-2">
              <label htmlFor="watch-symbol" className="sr-only">Kode saham</label>
              <input id="watch-symbol" className="input" placeholder="Kode (mis. BBCA)" value={addSym}
                     onChange={(e) => setAddSym(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add(addSym, addNote)} />
              <label htmlFor="watch-note" className="sr-only">Catatan</label>
              <input id="watch-note" className="input" placeholder="Catatan (opsional)" value={addNote}
                     onChange={(e) => setAddNote(e.target.value)} />
              <button className="btn btn-active w-full" onClick={() => add(addSym, addNote)}>+ Tambah</button>
            </div>
          </div>

          <div className="card">
            <div className="label px-3 pt-3 pb-1">Watchlist Saya ({items.length})</div>
            <div className="divide-y divide-border/40">
              {items.map((w) => (
                <div key={w.id} className="px-3 py-2 flex items-center justify-between">
                  <div>
                    <Link href={`/analyst?symbol=${w.symbol}`} className="text-sm font-semibold hover:text-accent">{w.symbol}</Link>
                    <div className="text-[10px] text-dim truncate max-w-[140px]">{w.note || "—"}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs font-mono">{w.price != null ? fmtPrice(w.price) : "–"}</div>
                    <div className={`text-[10px] ${w.score != null ? scoreColor(w.score) : "text-dim"}`}>
                      {w.score != null ? `skor ${w.score}` : "–"}
                    </div>
                  </div>
                  <button className="text-down text-xs hover:underline ml-2" onClick={() => remove(w.id)}>✕</button>
                </div>
              ))}
              {!items.length && <div className="px-3 py-6 text-xs text-dim">Belum ada. Tambah manual atau dari Screener →</div>}
            </div>
          </div>
        </div>

        {/* ── AI Picks ── */}
        <div className="space-y-3">
          <div className="card p-3 flex items-center justify-between flex-wrap gap-2">
            <div>
              <div className="label">🤖 AI Picks — Top Bullish Hari Ini</div>
              <div className="text-[11px] text-dim mt-0.5">
                {generating
                  ? "Sedang generate AI Picks…"
                  : lastBatchAt
                    ? `Digenerate ${timeAgo(lastBatchAt)}`
                    : "Belum ada batch — klik tombol untuk generate dengan AI"}
              </div>
            </div>
            <button className="btn btn-active text-xs" onClick={refresh} disabled={generating}>
              {generating ? "⏳ Memproses…" : aiPicks.length ? "↻ Generate ulang" : "🤖 Generate AI Picks"}
            </button>
          </div>

          {!aiPicks.length && !generating && (
            <div className="card p-8 text-center text-sm text-dim">
              Belum ada AI Picks. Klik “🤖 Generate AI Picks” untuk menganalisa seluruh universe IDX dengan AI.
            </div>
          )}
          {!aiPicks.length && generating && (
            <div className="card p-8 text-center text-sm text-dim">
              Menyiapkan AI Picks… ini bisa beberapa saat saat pertama kali.
            </div>
          )}

          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {aiPicks.map((p) => (
              <div key={p.id} className="card p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <Link href={`/analyst?symbol=${p.symbol}`} className="font-bold hover:text-accent">{p.symbol}</Link>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-mono font-bold ${scoreColor(p.score)}`}>skor {p.score}</span>
                    <button className="text-xs hover:underline disabled:opacity-40"
                            disabled={watchSet.has(p.symbol)} onClick={() => add(p.symbol)}
                            title="Tambah ke watchlist">{watchSet.has(p.symbol) ? "✓" : "★"}</button>
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <VerdictBadge v={p.verdict} />
                  <span className="text-[10px] text-dim">{p.sector || ""}</span>
                </div>
                <div className="grid grid-cols-3 gap-1 text-center text-[11px]">
                  <div className="bg-panel2 rounded py-1">
                    <div className="text-dim text-[9px]">Entry</div>
                    <div className="font-mono">{fmtPrice(p.entry_price)}</div>
                  </div>
                  <div className="bg-panel2 rounded py-1">
                    <div className="text-dim text-[9px]">Target</div>
                    <div className="font-mono text-up">{fmtPrice(p.target_price)}</div>
                  </div>
                  <div className="bg-panel2 rounded py-1">
                    <div className="text-dim text-[9px]">Cutloss</div>
                    <div className="font-mono text-down">{fmtPrice(p.cutloss_price)}</div>
                  </div>
                </div>
                <div className="text-[11px] leading-snug text-dim">
                  {p.reasoning
                    ? p.reasoning
                    : <span className="italic">Reasoning AI tidak tersedia</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
