"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ScreenerResult, WatchlistItem, ScreenerPreset } from "@/lib/types";
import { fmtPrice, fmtPct, colorOf } from "@/lib/format";

const INTERVALS = ["1d", "1h", "1wk"];

function scoreColor(s: number) {
  if (s >= 50) return "text-up";
  if (s >= 20) return "text-up/80";
  if (s <= -50) return "text-down";
  if (s <= -20) return "text-down/80";
  return "text-dim";
}
function VerdictBadge({ v }: { v: string }) {
  const map: Record<string, string> = {
    "STRONG BUY": "text-up border-up bg-up/10", "BUY": "text-up border-up/50 bg-up/5",
    "NEUTRAL": "text-dim border-border", "SELL": "text-down border-down/50 bg-down/5",
    "STRONG SELL": "text-down border-down bg-down/10",
  };
  return <span className={`chip border ${map[v] || "text-dim border-border"}`}>{v}</span>;
}

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [presets, setPresets] = useState<ScreenerPreset[]>([]);
  const [results, setResults] = useState<ScreenerResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [interval, setInterval] = useState("1d");
  const [activePreset, setActivePreset] = useState("strong_buy");
  const [addSym, setAddSym] = useState("");
  const [addNote, setAddNote] = useState("");

  // filters
  const [minScore, setMinScore] = useState<string>("");
  const [rsiBelow, setRsiBelow] = useState<string>("");
  const [minVol, setMinVol] = useState<string>("");
  const [aboveMa200, setAboveMa200] = useState(false);
  const [exclSpecial, setExclSpecial] = useState(true);

  const loadWatch = () => api.watchlist().then((d) => setItems(d.watchlist)).catch(() => {});

  const runScreen = (extra: Record<string, any> = {}) => {
    setLoading(true);
    const params: Record<string, any> = {
      interval, limit: 50, exclude_special: exclSpecial,
      min_score: minScore, rsi_below: rsiBelow, min_vol_ratio: minVol,
      above_ma200: aboveMa200, ...extra,
    };
    api.screener(params).then((d) => setResults(d.results)).catch(() => setResults([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    api.screenerPresets().then((d) => setPresets(d.presets)).catch(() => {});
    loadWatch();
    // initial: strong buy
    api.screener({ interval: "1d", min_score: 50, above_ma200: true, exclude_special: true, limit: 50 })
      .then((d) => setResults(d.results)).catch(() => {});
  }, []);

  const applyPreset = (p: ScreenerPreset) => {
    setActivePreset(p.key);
    // reset manual filters, apply preset params
    setMinScore(p.params.min_score ?? ""); setRsiBelow(p.params.rsi_below ?? "");
    setMinVol(p.params.min_vol_ratio ?? ""); setAboveMa200(!!p.params.above_ma200);
    setLoading(true);
    api.screener({ interval, exclude_special: exclSpecial, limit: 50, ...p.params })
      .then((d) => setResults(d.results)).catch(() => setResults([]))
      .finally(() => setLoading(false));
  };

  const add = async (sym: string, note?: string) => {
    if (!sym) return;
    try { await api.addWatchlist({ symbol: sym.toUpperCase(), note }); setAddSym(""); setAddNote(""); loadWatch(); }
    catch {}
  };
  const remove = async (id: number) => { await api.delWatchlist(id); loadWatch(); };

  const watchSet = useMemo(() => new Set(items.map((i) => i.symbol)), [items]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-6 py-4 border-b border-border">
        <h1 className="text-xl font-bold">Watchlist & Screener</h1>
        <p className="text-xs text-dim mt-0.5">Daily picks rule-based dari {results.length ? "" : ""}seluruh universe IDX · AI menyusul (Hermes/self-hosted)</p>
      </div>

      <div className="grid lg:grid-cols-[300px_1fr] gap-4 p-6">
        {/* ── Watchlist manual ── */}
        <div className="space-y-3">
          <div className="card p-3">
            <div className="label mb-2">Tambah ke Watchlist</div>
            <div className="space-y-2">
              <input className="input" placeholder="Kode (mis. BBCA)" value={addSym}
                     onChange={(e) => setAddSym(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add(addSym, addNote)} />
              <input className="input" placeholder="Catatan (opsional)" value={addNote}
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
              {!items.length && <div className="px-3 py-6 text-xs text-dim">Belum ada. Tambah manual atau dari screener →</div>}
            </div>
          </div>
        </div>

        {/* ── Screener ── */}
        <div className="space-y-3">
          <div className="card p-3 space-y-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="label">Preset:</span>
              {presets.map((p) => (
                <button key={p.key} onClick={() => applyPreset(p)}
                        className={`btn text-xs ${activePreset === p.key ? "btn-active" : ""}`}>{p.label}</button>
              ))}
            </div>
            <div className="flex items-center gap-3 flex-wrap text-xs">
              <label className="flex items-center gap-1">TF
                <select className="input !w-auto !py-1" value={interval} onChange={(e) => setInterval(e.target.value)}>
                  {INTERVALS.map((iv) => <option key={iv} value={iv}>{iv}</option>)}
                </select>
              </label>
              <label className="flex items-center gap-1">Min skor
                <input className="input !w-16 !py-1" type="number" value={minScore} onChange={(e) => setMinScore(e.target.value)} />
              </label>
              <label className="flex items-center gap-1">RSI &lt;
                <input className="input !w-16 !py-1" type="number" value={rsiBelow} onChange={(e) => setRsiBelow(e.target.value)} />
              </label>
              <label className="flex items-center gap-1">Vol× ≥
                <input className="input !w-16 !py-1" type="number" value={minVol} onChange={(e) => setMinVol(e.target.value)} />
              </label>
              <label className="flex items-center gap-1.5"><input type="checkbox" checked={aboveMa200} onChange={(e) => setAboveMa200(e.target.checked)} /> &gt; MA200</label>
              <label className="flex items-center gap-1.5"><input type="checkbox" checked={exclSpecial} onChange={(e) => setExclSpecial(e.target.checked)} /> Buang Pemantauan Khusus</label>
              <button className="btn btn-active text-xs" onClick={() => { setActivePreset(""); runScreen(); }}>Terapkan</button>
            </div>
          </div>

          <div className="card overflow-x-auto">
            <div className="flex items-center justify-between px-4 pt-3">
              <div className="label">Hasil Screener {loading ? "(memuat…)" : `(${results.length})`}</div>
            </div>
            <table className="w-full text-sm mt-2">
              <thead>
                <tr className="text-left text-dim text-xs border-b border-border">
                  {["#", "Kode", "Harga", "Chg%", "Skor", "Sinyal", "RSI", "Vol×", "vs MA200", "Papan", ""].map((h) =>
                    <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={r.symbol} className="border-b border-border/40 hover:bg-panel2">
                    <td className="px-3 py-2 text-dim">{i + 1}</td>
                    <td className="px-3 py-2">
                      <Link href={`/analyst?symbol=${r.symbol}`} className="font-semibold hover:text-accent">{r.symbol}</Link>
                      <div className="text-[10px] text-dim truncate max-w-[160px]">{r.name || ""}</div>
                    </td>
                    <td className="px-3 py-2 font-mono">{fmtPrice(r.close)}</td>
                    <td className={`px-3 py-2 font-mono ${colorOf(r.change_pct)}`}>{fmtPct(r.change_pct)}</td>
                    <td className={`px-3 py-2 font-mono font-bold ${scoreColor(r.score)}`}>{r.score}</td>
                    <td className="px-3 py-2"><VerdictBadge v={r.verdict} /></td>
                    <td className="px-3 py-2 font-mono">{r.rsi != null ? r.rsi.toFixed(0) : "–"}</td>
                    <td className="px-3 py-2 font-mono">{r.vol_ratio ? r.vol_ratio.toFixed(1) + "×" : "–"}</td>
                    <td className={`px-3 py-2 font-mono ${colorOf(r.dist_ma200_pct)}`}>{r.dist_ma200_pct != null ? fmtPct(r.dist_ma200_pct) : "–"}</td>
                    <td className="px-3 py-2 text-[10px] text-dim">{r.board || "–"}</td>
                    <td className="px-3 py-2">
                      <button className="text-xs hover:underline disabled:opacity-40"
                              disabled={watchSet.has(r.symbol)} onClick={() => add(r.symbol)}
                              title="Tambah ke watchlist">{watchSet.has(r.symbol) ? "✓" : "★"}</button>
                    </td>
                  </tr>
                ))}
                {!results.length && !loading && (
                  <tr><td colSpan={11} className="px-3 py-8 text-center text-dim text-sm">Tidak ada hasil. Longgarkan filter.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
