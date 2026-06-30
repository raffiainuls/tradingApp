"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, wsUrl } from "@/lib/api";
import type { HistoryResponse, Quote } from "@/lib/types";
import { fmtPrice, fmtPct, fmtVol, colorOf } from "@/lib/format";
import AnalystChart from "@/components/AnalystChart";
import IndicatorPanel, { INDICATORS } from "@/components/IndicatorPanel";
import TechnicalSummary from "@/components/TechnicalSummary";
import TickerTape from "@/components/TickerTape";

const INTERVALS = ["5m", "15m", "1h", "1d", "1wk"];
const DEFAULT_ACTIVE = new Set(["sma20", "sma50", "bbands", "vwap", "rsi", "macd"]);

export default function AnalystPage() {
  const [symbol, setSymbol] = useState("BBCA");
  const [interval, setInterval] = useState("1d");
  const [data, setData] = useState<HistoryResponse | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [active, setActive] = useState<Set<string>>(new Set(DEFAULT_ACTIVE));
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [quotesLoading, setQuotesLoading] = useState(true);
  const [wsStatus, setWsStatus] = useState<"live" | "off">("off");
  const wsRef = useRef<WebSocket | null>(null);

  // ── Preselect symbol dari ?symbol= (mis. dari Watchlist/Screener) ──
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const s = sp.get("symbol");
    if (s) setSymbol(s.toUpperCase());
  }, []);

  // ── Load history on symbol/interval change ──
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.history(symbol, interval)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => console.warn("history error", e))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, interval]);

  // ── Quotes for ticker list ──
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api.quotes(interval)
        .then((q) => { if (!cancelled) setQuotes(q); })
        .catch((e) => console.warn("quotes error", e))
        .finally(() => { if (!cancelled) setQuotesLoading(false); });
    load();
    const t = window.setInterval(load, 60000);
    return () => { cancelled = true; window.clearInterval(t); };
  }, [interval]);

  // ── Periodic refresh of current chart (indicators) ──
  useEffect(() => {
    const t = window.setInterval(() => {
      api.history(symbol, interval).then(setData).catch(() => {});
    }, 60000);
    return () => window.clearInterval(t);
  }, [symbol, interval]);

  // ── WebSocket live ──
  useEffect(() => {
    const ws = new WebSocket(`${wsUrl()}/ws`);
    wsRef.current = ws;
    ws.onopen = () => setWsStatus("live");
    ws.onclose = () => setWsStatus("off");
    ws.onerror = () => setWsStatus("off");
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type !== "bar") return;
        const d = msg.data;
        // update quote list
        setQuotes((prev) => {
          const i = prev.findIndex((q) => q.symbol === d.symbol);
          if (i === -1 || d.interval !== interval) return prev;
          const copy = [...prev];
          const prevClose = copy[i].price;
          copy[i] = { ...copy[i], price: d.close, volume: d.volume };
          return copy;
        });
        // update current chart's last candle
        if (d.symbol === symbol && d.interval === interval) {
          setData((prev) => {
            if (!prev) return prev;
            const candles = [...prev.candles];
            const last = candles[candles.length - 1];
            const bar = { time: d.epoch, open: d.open, high: d.high, low: d.low, close: d.close, volume: d.volume };
            if (last && last.time === d.epoch) candles[candles.length - 1] = bar;
            else if (last && d.epoch > last.time) candles.push(bar);
            return { ...prev, candles };
          });
        }
      } catch {}
    };
    return () => ws.close();
  }, [symbol, interval]);

  const overlays = useMemo(
    () => new Set([...active].filter((k) => INDICATORS.find((i) => i.key === k)?.kind === "overlay")),
    [active]
  );
  const oscillators = useMemo(
    () => INDICATORS.filter((i) => i.kind === "oscillator" && active.has(i.key)).map((i) => i.key),
    [active]
  );

  const toggle = (key: string) =>
    setActive((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  const curQuote = quotes.find((q) => q.symbol === symbol);
  const filtered = quotes.filter((q) => !search || q.symbol.includes(search.toUpperCase()));

  return (
    <div className="flex flex-col h-full">
     <div className="flex flex-1 min-h-0">
      {/* ── Symbol list ── */}
      <div className="w-52 shrink-0 border-r border-border flex flex-col bg-panel">
        <div className="p-2 border-b border-border">
          <input
            className="input"
            placeholder="Cari saham…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="text-[10px] text-dim mt-1 px-1">
            {quotesLoading ? "memuat…" : `${filtered.length} emiten`}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {filtered.map((q) => (
            <button
              key={q.symbol}
              onClick={() => setSymbol(q.symbol)}
              className={`w-full flex items-center justify-between px-3 py-2 text-left border-b border-border/40 hover:bg-panel2 transition-colors ${
                q.symbol === symbol ? "bg-accent/10 border-l-2 border-l-accent" : ""
              }`}
            >
              <div>
                <div className="text-sm font-semibold">{q.symbol}</div>
                <div className="text-[10px] text-dim">{q.sector || q.type}</div>
              </div>
              <div className="text-right">
                <div className="text-xs font-mono">{fmtPrice(q.price)}</div>
                <div className={`text-[10px] font-mono ${colorOf(q.change_pct)}`}>{fmtPct(q.change_pct)}</div>
              </div>
            </button>
          ))}
          {quotesLoading && !filtered.length && (
            <div className="p-4 text-xs text-dim">Memuat daftar emiten…</div>
          )}
          {!quotesLoading && !filtered.length && (
            <div className="p-4 text-xs text-dim">
              {search ? `Tidak ada emiten cocok "${search}".` : "Belum ada data. Tunggu poller mengisi…"}
            </div>
          )}
        </div>
      </div>

      {/* ── Chart area ── */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
          <div className="flex items-baseline gap-3">
            <h1 className="text-xl font-bold">{symbol}</h1>
            <span className="text-sm text-dim">{curQuote?.sector || ""}</span>
            {curQuote && (
              <>
                <span className="text-lg font-mono">{fmtPrice(curQuote.price)}</span>
                <span className={`text-sm font-mono ${colorOf(curQuote.change_pct)}`}>
                  {fmtPct(curQuote.change_pct)}
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] px-2 py-0.5 rounded-full ${wsStatus === "live" ? "bg-up/15 text-up" : "bg-down/15 text-down"}`}>
              {wsStatus === "live" ? "● LIVE" : "○ OFFLINE"}
            </span>
            <div className="flex gap-1">
              {INTERVALS.map((iv) => (
                <button
                  key={iv}
                  onClick={() => setInterval(iv)}
                  className={`btn ${interval === iv ? "btn-active" : ""}`}
                >
                  {iv}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex-1 min-h-0 relative">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center text-dim text-sm z-20 pointer-events-none">
              Memuat…
            </div>
          )}
          {data && data.candles.length > 0 ? (
            <AnalystChart data={data} overlays={overlays} oscillators={oscillators} />
          ) : (
            !loading && (
              <div className="absolute inset-0 flex items-center justify-center text-dim text-sm">
                Belum ada data untuk {symbol} ({interval}). Poller mengambil data dari yFinance tiap 60 detik.
              </div>
            )
          )}
        </div>
      </div>

      {/* ── Right panel ── */}
      <div className="w-72 shrink-0 border-l border-border flex flex-col bg-panel overflow-y-auto">
        <div className="p-3 border-b border-border">
          <div className="label mb-2">Indikator</div>
          <IndicatorPanel active={active} onToggle={toggle} />
        </div>
        <div className="p-3">
          <div className="label mb-2">Ringkasan Teknikal</div>
          {data?.signals ? <TechnicalSummary s={data.signals} /> : <div className="text-xs text-dim">–</div>}
        </div>
      </div>
     </div>

      {/* ── Ticker tape (footer) ── */}
      <TickerTape quotes={quotes} />
    </div>
  );
}
