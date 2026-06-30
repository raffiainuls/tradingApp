"use client";
import { useMemo } from "react";
import { fmtMoney } from "@/lib/format";

export default function EquityCurve({ data }: { data: { date: string; equity: number }[] }) {
  const path = useMemo(() => {
    if (data.length < 2) return null;
    const W = 600, H = 180, pad = 8;
    const eq = data.map((d) => d.equity);
    const min = Math.min(0, ...eq), max = Math.max(0, ...eq);
    const rng = max - min || 1;
    const x = (i: number) => pad + (i / (data.length - 1)) * (W - 2 * pad);
    const y = (v: number) => H - pad - ((v - min) / rng) * (H - 2 * pad);
    const line = data.map((d, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(d.equity).toFixed(1)}`).join(" ");
    const area = `${line} L ${x(data.length - 1).toFixed(1)} ${y(min)} L ${x(0).toFixed(1)} ${y(min)} Z`;
    const zeroY = y(0);
    const last = data[data.length - 1].equity;
    return { line, area, zeroY, W, H, up: last >= 0 };
  }, [data]);

  if (!path) return <div className="text-xs text-dim p-4">Belum ada trade tertutup untuk equity curve.</div>;

  const color = path.up ? "#16c784" : "#ea3943";
  return (
    <div>
      <svg viewBox={`0 0 ${path.W} ${path.H}`} className="w-full" preserveAspectRatio="none" style={{ height: 180 }}>
        <defs>
          <linearGradient id="eqg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" y1={path.zeroY} x2={path.W} y2={path.zeroY} stroke="#1f2940" strokeWidth="1" strokeDasharray="4 4" />
        <path d={path.area} fill="url(#eqg)" />
        <path d={path.line} fill="none" stroke={color} strokeWidth="2" />
      </svg>
      <div className="flex justify-between text-[10px] text-dim mt-1">
        <span>{data[0].date}</span>
        <span className={path.up ? "text-up" : "text-down"}>
          Kumulatif: {fmtMoney(data[data.length - 1].equity)}
        </span>
        <span>{data[data.length - 1].date}</span>
      </div>
    </div>
  );
}
