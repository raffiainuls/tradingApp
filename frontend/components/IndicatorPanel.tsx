"use client";

export interface IndicatorDef { key: string; label: string; kind: "overlay" | "oscillator"; group: string; }

export const INDICATORS: IndicatorDef[] = [
  // Overlays
  { key: "sma20", label: "SMA 20", kind: "overlay", group: "Trend" },
  { key: "sma50", label: "SMA 50", kind: "overlay", group: "Trend" },
  { key: "sma200", label: "SMA 200", kind: "overlay", group: "Trend" },
  { key: "ema20", label: "EMA 20", kind: "overlay", group: "Trend" },
  { key: "ema50", label: "EMA 50", kind: "overlay", group: "Trend" },
  { key: "sar", label: "Parabolic SAR", kind: "overlay", group: "Trend" },
  { key: "bbands", label: "Bollinger Bands", kind: "overlay", group: "Volatility" },
  { key: "keltner", label: "Keltner Channel", kind: "overlay", group: "Volatility" },
  { key: "vwap", label: "VWAP", kind: "overlay", group: "Volume" },
  { key: "volprofile", label: "Vol Profile (POC)", kind: "overlay", group: "Volume" },
  // Oscillators
  { key: "rsi", label: "RSI", kind: "oscillator", group: "Momentum" },
  { key: "stoch", label: "Stochastic", kind: "oscillator", group: "Momentum" },
  { key: "williams", label: "Williams %R", kind: "oscillator", group: "Momentum" },
  { key: "cci", label: "CCI", kind: "oscillator", group: "Momentum" },
  { key: "macd", label: "MACD", kind: "oscillator", group: "Trend" },
  { key: "adx", label: "ADX / DMI", kind: "oscillator", group: "Trend" },
  { key: "atr", label: "ATR", kind: "oscillator", group: "Volatility" },
  { key: "obv", label: "OBV", kind: "oscillator", group: "Volume" },
  { key: "ad", label: "A/D Line", kind: "oscillator", group: "Volume" },
];

const GROUPS = ["Trend", "Momentum", "Volatility", "Volume"];

export default function IndicatorPanel({
  active, onToggle,
}: { active: Set<string>; onToggle: (key: string) => void }) {
  return (
    <div className="space-y-4">
      {GROUPS.map((g) => {
        const items = INDICATORS.filter((i) => i.group === g);
        return (
          <div key={g}>
            <div className="label mb-1.5">{g}</div>
            <div className="flex flex-wrap gap-1.5">
              {items.map((i) => (
                <button
                  key={i.key}
                  onClick={() => onToggle(i.key)}
                  className={`btn text-xs ${active.has(i.key) ? "btn-active" : ""}`}
                  title={i.kind === "overlay" ? "Overlay di chart harga" : "Panel terpisah"}
                >
                  {i.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
