"use client";
import { useEffect, useRef } from "react";
import {
  createChart, ColorType, LineStyle, CrosshairMode,
  type IChartApi, type ISeriesApi, type Time,
} from "lightweight-charts";
import type { HistoryResponse, LinePoint } from "@/lib/types";

const CHART_BG = "#0a0e17";
const GRID = "#141b2c";
const BORDER = "#1f2940";
const TEXT = "#7d8aa8";

const OVERLAY_COLORS: Record<string, string> = {
  sma20: "#f7a440", sma50: "#3d8bff", sma200: "#b15dff",
  ema20: "#16c784", ema50: "#ff7ac6", vwap: "#f7d046",
  bb: "#5a6b94", kc: "#3f8f8f", sar: "#b15dff",
};

interface Props {
  data: HistoryResponse;
  overlays: Set<string>;     // sma20, sma50, sma200, ema20, ema50, bbands, keltner, vwap, sar, volprofile
  oscillators: string[];     // rsi, macd, stoch, williams, cci, adx, atr, obv, ad
}

const baseChartOpts = {
  // locale eksplisit: hindari ketergantungan pada data ICU browser (sebagian
  // environment melempar RangeError "Incorrect locale information provided")
  localization: { locale: "en-US" },
  layout: { background: { type: ColorType.Solid, color: CHART_BG }, textColor: TEXT, fontSize: 11 },
  grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
  rightPriceScale: { borderColor: BORDER },
  timeScale: { borderColor: BORDER, timeVisible: true, secondsVisible: false },
  crosshair: { mode: CrosshairMode.Normal },
};

export default function AnalystChart({ data, overlays, oscillators }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const oscWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mainRef.current || !oscWrapRef.current) return;
    const candles = data.candles;
    if (!candles.length) return;

    const charts: IChartApi[] = [];
    const cleanups: (() => void)[] = [];

    // ── Main price chart ──
    const main = createChart(mainRef.current, {
      ...baseChartOpts,
      width: mainRef.current.clientWidth,
      height: mainRef.current.clientHeight,
    });
    charts.push(main);

    const candleSeries = main.addCandlestickSeries({
      upColor: "#16c784", downColor: "#ea3943",
      borderVisible: false, wickUpColor: "#16c784", wickDownColor: "#ea3943",
    });
    candleSeries.setData(
      candles.map((c) => ({ time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close }))
    );

    const volSeries = main.addHistogramSeries({
      priceFormat: { type: "volume" }, priceScaleId: "vol",
    });
    main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
    volSeries.setData(
      candles.map((c) => ({
        time: c.time as Time, value: c.volume,
        color: c.close >= c.open ? "rgba(22,199,132,0.4)" : "rgba(234,57,67,0.4)",
      }))
    );

    // ── Overlays ──
    const ind = data.indicators;
    const addLine = (pts: LinePoint[] | undefined, color: string, width = 1, dashed = false) => {
      if (!pts || !pts.length) return;
      const s = main.addLineSeries({
        color, lineWidth: width as any, priceLineVisible: false, lastValueVisible: false,
        lineStyle: dashed ? LineStyle.Dotted : LineStyle.Solid,
      });
      s.setData(pts.map((p) => ({ time: p.time as Time, value: p.value })));
    };

    if (overlays.has("sma20")) addLine(ind.sma20, OVERLAY_COLORS.sma20);
    if (overlays.has("sma50")) addLine(ind.sma50, OVERLAY_COLORS.sma50);
    if (overlays.has("sma200")) addLine(ind.sma200, OVERLAY_COLORS.sma200);
    if (overlays.has("ema20")) addLine(ind.ema20, OVERLAY_COLORS.ema20);
    if (overlays.has("ema50")) addLine(ind.ema50, OVERLAY_COLORS.ema50);
    if (overlays.has("vwap")) addLine(ind.vwap, OVERLAY_COLORS.vwap, 2);
    if (overlays.has("sar")) addLine(ind.sar, OVERLAY_COLORS.sar, 1, true);
    if (overlays.has("bbands") && ind.bbands) {
      addLine(ind.bbands.upper, OVERLAY_COLORS.bb);
      addLine(ind.bbands.middle, OVERLAY_COLORS.bb + "99");
      addLine(ind.bbands.lower, OVERLAY_COLORS.bb);
    }
    if (overlays.has("keltner") && ind.keltner) {
      addLine(ind.keltner.upper, OVERLAY_COLORS.kc);
      addLine(ind.keltner.lower, OVERLAY_COLORS.kc);
    }
    if (overlays.has("volprofile") && ind.volprofile?.poc) {
      candleSeries.createPriceLine({
        price: ind.volprofile.poc, color: "#f7d046", lineWidth: 1,
        lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "POC",
      });
    }

    main.timeScale().fitContent();

    // ── Oscillator panes ──
    oscWrapRef.current.innerHTML = "";
    const makePane = (title: string) => {
      const wrap = document.createElement("div");
      wrap.className = "relative border-t border-border";
      wrap.style.height = "130px";
      const lbl = document.createElement("div");
      lbl.className = "absolute top-1 left-2 z-10 text-[10px] text-dim font-mono pointer-events-none";
      lbl.textContent = title;
      wrap.appendChild(lbl);
      oscWrapRef.current!.appendChild(wrap);
      const c = createChart(wrap, {
        ...baseChartOpts,
        width: wrap.clientWidth, height: 130,
        timeScale: { ...baseChartOpts.timeScale, visible: false },
      });
      charts.push(c);
      return c;
    };

    const guide = (chart: IChartApi, series: ISeriesApi<"Line">, level: number, color: string) => {
      series.createPriceLine({ price: level, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
    };
    const setLine = (chart: IChartApi, pts: LinePoint[] | undefined, color: string, width = 1) => {
      const s = chart.addLineSeries({ color, lineWidth: width as any, priceLineVisible: false, lastValueVisible: true });
      if (pts) s.setData(pts.map((p) => ({ time: p.time as Time, value: p.value })));
      return s;
    };

    for (const osc of oscillators) {
      if (osc === "rsi" && ind.rsi) {
        const c = makePane("RSI (14)");
        const s = setLine(c, ind.rsi, "#3d8bff", 1.5);
        guide(c, s, 70, "#ea394366"); guide(c, s, 30, "#16c78466");
        c.timeScale().fitContent();
      } else if (osc === "macd" && ind.macd) {
        const c = makePane("MACD (12,26,9)");
        const h = c.addHistogramSeries({ priceLineVisible: false });
        h.setData(ind.macd.hist.map((p) => ({
          time: p.time as Time, value: p.value,
          color: p.value >= 0 ? "rgba(22,199,132,0.5)" : "rgba(234,57,67,0.5)",
        })));
        setLine(c, ind.macd.macd, "#3d8bff", 1.5);
        setLine(c, ind.macd.signal, "#f7a440", 1.5);
        c.timeScale().fitContent();
      } else if (osc === "stoch" && ind.stoch) {
        const c = makePane("Stochastic (14,3)");
        const s = setLine(c, ind.stoch.k, "#3d8bff", 1.5);
        setLine(c, ind.stoch.d, "#f7a440", 1.5);
        guide(c, s, 80, "#ea394366"); guide(c, s, 20, "#16c78466");
        c.timeScale().fitContent();
      } else if (osc === "williams" && ind.williams) {
        const c = makePane("Williams %R (14)");
        const s = setLine(c, ind.williams, "#b15dff", 1.5);
        guide(c, s, -20, "#ea394366"); guide(c, s, -80, "#16c78466");
        c.timeScale().fitContent();
      } else if (osc === "cci" && ind.cci) {
        const c = makePane("CCI (20)");
        const s = setLine(c, ind.cci, "#f7d046", 1.5);
        guide(c, s, 100, "#ea394366"); guide(c, s, -100, "#16c78466");
        c.timeScale().fitContent();
      } else if (osc === "adx" && ind.adx) {
        const c = makePane("ADX (14)");
        const s = setLine(c, ind.adx.adx, "#e2e8f5", 2);
        setLine(c, ind.adx.plus_di, "#16c784", 1);
        setLine(c, ind.adx.minus_di, "#ea3943", 1);
        guide(c, s, 25, "#7d8aa866");
        c.timeScale().fitContent();
      } else if (osc === "atr" && ind.atr) {
        const c = makePane("ATR (14)");
        setLine(c, ind.atr, "#f7a440", 1.5);
        c.timeScale().fitContent();
      } else if (osc === "obv" && ind.obv) {
        const c = makePane("OBV");
        setLine(c, ind.obv, "#16c784", 1.5);
        c.timeScale().fitContent();
      } else if (osc === "ad" && ind.ad) {
        const c = makePane("A/D Line");
        setLine(c, ind.ad, "#3d8bff", 1.5);
        c.timeScale().fitContent();
      }
    }

    // ── Sync time scales across all panes ──
    let syncing = false;
    const sync = (src: IChartApi) =>
      src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return;
        syncing = true;
        for (const c of charts) if (c !== src) c.timeScale().setVisibleLogicalRange(range);
        syncing = false;
      });
    charts.forEach(sync);

    // crosshair sync
    let chSync = false;
    charts.forEach((src) => {
      src.subscribeCrosshairMove((param) => {
        if (chSync) return;
        chSync = true;
        chSync = false;
      });
    });

    // ── Resize ──
    const onResize = () => {
      if (mainRef.current) main.applyOptions({ width: mainRef.current.clientWidth, height: mainRef.current.clientHeight });
      const panes = oscWrapRef.current?.children;
      if (panes) {
        let i = 1;
        for (const c of charts.slice(1)) {
          const el = panes[i - 1] as HTMLElement;
          if (el) c.applyOptions({ width: el.clientWidth, height: 130 });
          i++;
        }
      }
    };
    window.addEventListener("resize", onResize);
    cleanups.push(() => window.removeEventListener("resize", onResize));

    return () => {
      cleanups.forEach((f) => f());
      charts.forEach((c) => c.remove());
    };
  }, [data, overlays, oscillators]);

  return (
    <div className="flex flex-col h-full">
      <div ref={mainRef} className="flex-1 min-h-0" />
      <div ref={oscWrapRef} />
    </div>
  );
}
