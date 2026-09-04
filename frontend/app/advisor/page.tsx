"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AiAdvisorAnalysis, AiAdvisorDailyPicks, BrokerSummaryAnalysis } from "@/lib/types";
import { fmtPrice, fmtPct, fmtMoney, colorOf, scoreColor } from "@/lib/format";
import TechnicalSummary from "@/components/TechnicalSummary";
import VerdictBadge from "@/components/VerdictBadge";

function friendlyError(e: unknown): string {
  const msg = e instanceof Error ? e.message : "Terjadi kesalahan";
  const m = msg.match(/"detail":"([^"]+)"/);
  return m ? m[1] : msg;
}

export default function AdvisorPage() {
  const [symbol, setSymbol] = useState("BBCA");
  const [analysis, setAnalysis] = useState<AiAdvisorAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const [daily, setDaily] = useState<AiAdvisorDailyPicks | null>(null);
  const [dailyLoading, setDailyLoading] = useState(false);
  const [dailyError, setDailyError] = useState<string | null>(null);

  // ── Broker Summary per-saham (on-demand, quota IndexAlpha terbatas) ──
  const [brokerOpen, setBrokerOpen] = useState<string | null>(null);
  const [brokerLoading, setBrokerLoading] = useState<string | null>(null);
  const [brokerResults, setBrokerResults] = useState<Record<string, BrokerSummaryAnalysis>>({});
  const [brokerErrors, setBrokerErrors] = useState<Record<string, string>>({});

  // ── Preselect symbol dari ?symbol= (mis. dari Watchlist/Screener) ──
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const s = sp.get("symbol");
    if (s) setSymbol(s.toUpperCase());
  }, []);

  const analyze = async () => {
    if (!symbol) return;
    setAnalyzing(true); setAnalysisError(null); setAnalysis(null);
    try {
      setAnalysis(await api.aiAdvisorAnalysis(symbol.toUpperCase()));
    } catch (e) {
      setAnalysisError(friendlyError(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const generateDaily = async () => {
    setDailyLoading(true); setDailyError(null);
    try {
      setDaily(await api.aiAdvisorDailyPicks());
    } catch (e) {
      setDailyError(friendlyError(e));
    } finally {
      setDailyLoading(false);
    }
  };

  const toggleBrokerSummary = async (sym: string) => {
    if (brokerOpen === sym) { setBrokerOpen(null); return; }
    setBrokerOpen(sym);
    if (brokerResults[sym] || brokerLoading === sym) return;
    setBrokerLoading(sym);
    setBrokerErrors((prev) => { const n = { ...prev }; delete n[sym]; return n; });
    try {
      const res = await api.aiAdvisorBrokerSummary(sym);
      setBrokerResults((prev) => ({ ...prev, [sym]: res }));
    } catch (e) {
      setBrokerErrors((prev) => ({ ...prev, [sym]: friendlyError(e) }));
    } finally {
      setBrokerLoading(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-6 py-4 border-b border-border">
        <h1 className="text-xl font-bold">AI Advisor</h1>
        <p className="text-xs text-dim mt-0.5">
          Analisa mendalam per-saham & rekomendasi harian via Hermes Agent — second opinion naratif,
          beda mekanisme dari AI Picks otomatis di Watchlist
        </p>
      </div>

      <div className="p-6 space-y-8">
        {/* ── Analisa per-saham ── */}
        <div className="space-y-3">
          <div className="label">🔍 Analisa Saham</div>
          <div className="card p-3 flex items-center gap-2 flex-wrap">
            <input className="input !w-40" placeholder="Kode (mis. BBCA)" value={symbol}
                   onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                   onKeyDown={(e) => e.key === "Enter" && analyze()} />
            <button className="btn btn-active text-xs" onClick={analyze} disabled={analyzing || !symbol}>
              {analyzing ? "⏳ Menganalisa… (bisa ~1 menit)" : "Analisa dengan AI"}
            </button>
          </div>

          {analysisError && <div className="card p-4 text-sm text-down">{analysisError}</div>}

          {analysis && (
            <div className="grid lg:grid-cols-[320px_1fr] gap-4">
              <TechnicalSummary s={analysis.technical} />
              <div className="space-y-3">
                <div className="card p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="font-bold text-lg">{analysis.symbol}</span>
                      <span className="text-xs text-dim ml-2">{analysis.name || ""}</span>
                    </div>
                    <span className="text-[10px] text-dim">Data per {analysis.data_as_of}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center text-xs">
                    <div className="bg-panel2 rounded py-2">
                      <div className="text-dim text-[10px]">Entry</div>
                      <div className="font-mono">{fmtPrice(analysis.technical.entry_price)}</div>
                    </div>
                    <div className="bg-panel2 rounded py-2">
                      <div className="text-dim text-[10px]">Target</div>
                      <div className="font-mono text-up">{fmtPrice(analysis.technical.target_price)}</div>
                    </div>
                    <div className="bg-panel2 rounded py-2">
                      <div className="text-dim text-[10px]">Cutloss</div>
                      <div className="font-mono text-down">{fmtPrice(analysis.technical.cutloss_price)}</div>
                    </div>
                  </div>
                </div>
                <div className="card p-4">
                  <div className="label mb-2">🤖 Narasi AI Advisor (Hermes)</div>
                  <div className="text-sm leading-relaxed whitespace-pre-line">
                    {analysis.ai_narrative
                      ? analysis.ai_narrative
                      : <span className="italic text-dim">Narasi AI tidak tersedia (Hermes bridge tidak terjangkau).</span>}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Rekomendasi hari ini ── */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="label">📅 Rekomendasi Hari Ini</div>
            <button className="btn btn-active text-xs" onClick={generateDaily} disabled={dailyLoading}>
              {dailyLoading ? "⏳ Memproses…" : "🤖 Generate Rekomendasi"}
            </button>
          </div>

          {dailyError && <div className="card p-4 text-sm text-down">{dailyError}</div>}

          {daily && (
            <div className="space-y-3">
              {daily.data_as_of && <div className="text-[11px] text-dim">Data per {daily.data_as_of}</div>}
              <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-2">
                {daily.candidates.map((c) => (
                  <div key={c.symbol} className="card p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold">{c.symbol}</span>
                      <span className={`text-xs font-mono font-bold ${scoreColor(c.score)}`}>{c.score}</span>
                    </div>
                    <div className="flex items-center justify-between mt-1">
                      <VerdictBadge v={c.verdict} />
                      <span className={`text-xs font-mono ${colorOf(c.change_pct)}`}>{fmtPct(c.change_pct)}</span>
                    </div>
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-border">
                      <Link href={`/analyst?symbol=${c.symbol}`} className="text-[11px] text-dim hover:text-txt">
                        Lihat chart →
                      </Link>
                      <button
                        className="text-[11px] text-accent hover:underline"
                        onClick={() => toggleBrokerSummary(c.symbol)}
                      >
                        {brokerLoading === c.symbol ? "⏳ Menganalisa…" : "📊 Broker Summary"}
                      </button>
                    </div>
                  </div>
                ))}
                {!daily.candidates.length && (
                  <div className="col-span-full text-xs text-dim p-4">Tidak ada kandidat bullish saat ini.</div>
                )}
              </div>

              {brokerOpen && (
                <div className="card p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="label">📊 Broker Summary — {brokerOpen}</div>
                    <button className="text-xs text-dim hover:text-txt" onClick={() => setBrokerOpen(null)}>✕ Tutup</button>
                  </div>

                  {brokerLoading === brokerOpen && (
                    <div className="text-sm text-dim italic">⏳ Mengambil data broker & minta interpretasi AI…</div>
                  )}
                  {brokerErrors[brokerOpen] && (
                    <div className="text-sm text-down">{brokerErrors[brokerOpen]}</div>
                  )}
                  {brokerResults[brokerOpen] && (() => {
                    const b = brokerResults[brokerOpen];
                    return (
                      <div className="space-y-3">
                        <div className="text-[11px] text-dim">
                          Data per {b.date} · {b.broker_count} broker aktif · sumber: {b.source === "cache" ? "cache" : "live"}
                        </div>
                        <div className="grid sm:grid-cols-2 gap-3">
                          <div>
                            <div className="text-[11px] text-dim mb-1">Top Net Buy</div>
                            <div className="space-y-1">
                              {b.top_buy.length ? b.top_buy.map((r) => (
                                <div key={r.broker_code} className="flex items-center justify-between text-xs font-mono">
                                  <span>{r.broker_code}</span>
                                  <span className="text-up">{fmtMoney(r.buy_value - r.sell_value)}</span>
                                </div>
                              )) : <div className="text-xs text-dim italic">Tidak ada net-buy signifikan</div>}
                            </div>
                          </div>
                          <div>
                            <div className="text-[11px] text-dim mb-1">Top Net Sell</div>
                            <div className="space-y-1">
                              {b.top_sell.length ? b.top_sell.map((r) => (
                                <div key={r.broker_code} className="flex items-center justify-between text-xs font-mono">
                                  <span>{r.broker_code}</span>
                                  <span className="text-down">{fmtMoney(r.buy_value - r.sell_value)}</span>
                                </div>
                              )) : <div className="text-xs text-dim italic">Tidak ada net-sell signifikan</div>}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-xs bg-panel2 rounded px-3 py-2">
                          <span className="text-dim">Net value pasar (semua broker)</span>
                          <span className={`font-mono font-bold ${colorOf(b.net_value)}`}>{fmtMoney(b.net_value)}</span>
                        </div>
                        <div>
                          <div className="label mb-1">🤖 Interpretasi AI (Hermes)</div>
                          <div className="text-sm leading-relaxed whitespace-pre-line">
                            {b.ai_narrative
                              ? b.ai_narrative
                              : <span className="italic text-dim">Narasi AI tidak tersedia (Hermes bridge tidak terjangkau) — data mentah di atas tetap valid.</span>}
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}

              {daily.ai_commentary && (
                <div className="card p-4">
                  <div className="label mb-2">🤖 Ringkasan Pasar (Hermes)</div>
                  <div className="text-sm leading-relaxed whitespace-pre-line">{daily.ai_commentary}</div>
                </div>
              )}
              {!daily.ai_commentary && daily.candidates.length > 0 && (
                <div className="card p-4 text-sm italic text-dim">
                  Ringkasan AI tidak tersedia (Hermes bridge tidak terjangkau).
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
