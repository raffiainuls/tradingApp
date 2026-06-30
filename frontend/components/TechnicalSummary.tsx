"use client";
import type { Signals } from "@/lib/types";
import { fmtPrice, colorOf } from "@/lib/format";

const VERDICT_STYLE: Record<string, string> = {
  "STRONG BUY": "text-up border-up bg-up/10",
  "BUY": "text-up border-up/60 bg-up/5",
  "NEUTRAL": "text-dim border-border bg-panel2",
  "SELL": "text-down border-down/60 bg-down/5",
  "STRONG SELL": "text-down border-down bg-down/10",
};

function Row({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border/50 last:border-0">
      <span className="text-xs text-dim">{label}</span>
      <span className="text-sm font-mono" title={hint}>{value}</span>
    </div>
  );
}

export default function TechnicalSummary({ s }: { s: Signals }) {
  if (!s || s.verdict == null) {
    return <div className="text-xs text-dim p-4">Data belum cukup untuk analisis.</div>;
  }
  const score = s.score ?? 0;
  const gaugePct = ((score + 100) / 200) * 100;

  const rsiLabel = s.rsi == null ? "–" : s.rsi > 70 ? "Overbought" : s.rsi < 30 ? "Oversold" : "Netral";
  const macdLabel = s.macd_hist == null ? "–" : s.macd_hist > 0 ? "Bullish" : "Bearish";
  const trendLabel =
    s.close == null || s.sma50 == null ? "–" : s.close > s.sma50 ? "Uptrend" : "Downtrend";
  const adxLabel =
    s.adx == null ? "–" : s.adx > 25 ? "Kuat" : s.adx > 20 ? "Sedang" : "Lemah";

  return (
    <div className="space-y-3">
      <div className={`rounded-lg border p-3 text-center ${VERDICT_STYLE[s.verdict] || VERDICT_STYLE.NEUTRAL}`}>
        <div className="text-[10px] uppercase tracking-wider opacity-70">Technical Verdict</div>
        <div className="text-xl font-bold mt-0.5">{s.verdict}</div>
        <div className="mt-2 h-1.5 bg-bg rounded-full overflow-hidden">
          <div
            className="h-full bg-current transition-all"
            style={{ width: `${gaugePct}%` }}
          />
        </div>
        <div className="text-[10px] mt-1 opacity-70">Score: {score} / 100</div>
      </div>

      <div className="card p-3">
        <Row label="Harga" value={fmtPrice(s.close)} />
        <Row label="RSI (14)" value={<span className={s.rsi != null && (s.rsi > 70 || s.rsi < 30) ? "text-warn" : ""}>{s.rsi?.toFixed(1) ?? "–"} · {rsiLabel}</span>} />
        <Row label="MACD" value={<span className={colorOf(s.macd_hist)}>{macdLabel}</span>} />
        <Row label="Trend (vs SMA50)" value={<span className={s.close && s.sma50 ? colorOf(s.close - s.sma50) : ""}>{trendLabel}</span>} />
        <Row label="ADX" value={`${s.adx?.toFixed(1) ?? "–"} · ${adxLabel}`} />
      </div>

      <div className="card p-3">
        <div className="label mb-1.5">Key Levels</div>
        <Row label="SMA 20" value={fmtPrice(s.sma20)} />
        <Row label="SMA 50" value={fmtPrice(s.sma50)} />
        <Row label="SMA 200" value={fmtPrice(s.sma200)} />
        <Row label="BB Upper" value={fmtPrice(s.bb_upper)} />
        <Row label="BB Lower" value={fmtPrice(s.bb_lower)} />
        <Row label="ATR (14)" value={fmtPrice(s.atr)} hint="Volatilitas — acuan jarak cut loss" />
      </div>
    </div>
  );
}
