"use client";
import { useState } from "react";
import type { Position } from "@/lib/types";

const SECTORS = ["Banking", "Telco", "Consumer", "Energy", "Mining", "Healthcare",
  "Industrials", "Basic Materials", "Retail", "Tech", "Property", "Lainnya"];

export default function PositionForm({
  initial, onSubmit, onCancel,
}: {
  initial?: Partial<Position>;
  onSubmit: (data: any) => Promise<void>;
  onCancel: () => void;
}) {
  const [f, setF] = useState({
    symbol: initial?.symbol || "",
    lots: initial?.lots || 1,
    avg_price: initial?.avg_price || 0,
    buy_date: initial?.buy_date?.slice(0, 10) || new Date().toISOString().slice(0, 10),
    target_price: initial?.target_price ?? "",
    cutloss_price: initial?.cutloss_price ?? "",
    sector: initial?.sector || "Banking",
    reason: initial?.reason || "",
    tags: (initial?.tags || []).join(", "),
    notes: initial?.notes || "",
  });
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    setBusy(true);
    try {
      await onSubmit({
        symbol: f.symbol.toUpperCase(),
        lots: Number(f.lots),
        avg_price: Number(f.avg_price),
        buy_date: f.buy_date,
        target_price: f.target_price === "" ? null : Number(f.target_price),
        cutloss_price: f.cutloss_price === "" ? null : Number(f.cutloss_price),
        sector: f.sector,
        reason: f.reason || null,
        tags: f.tags ? f.tags.split(",").map((s) => s.trim()).filter(Boolean) : null,
        notes: f.notes || null,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card p-4 space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <div className="label mb-1">Kode</div>
          <input className="input" value={f.symbol} onChange={(e) => set("symbol", e.target.value)} placeholder="BBCA" />
        </div>
        <div>
          <div className="label mb-1">Lot</div>
          <input className="input" type="number" value={f.lots} onChange={(e) => set("lots", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Harga Beli</div>
          <input className="input" type="number" value={f.avg_price} onChange={(e) => set("avg_price", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Tgl Beli</div>
          <input className="input" type="date" value={f.buy_date} onChange={(e) => set("buy_date", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Target</div>
          <input className="input" type="number" value={f.target_price} onChange={(e) => set("target_price", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Cut Loss</div>
          <input className="input" type="number" value={f.cutloss_price} onChange={(e) => set("cutloss_price", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Sektor</div>
          <select className="input" value={f.sector} onChange={(e) => set("sector", e.target.value)}>
            {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <div className="label mb-1">Tags</div>
          <input className="input" value={f.tags} onChange={(e) => set("tags", e.target.value)} placeholder="breakout, dividen" />
        </div>
      </div>
      <div>
        <div className="label mb-1">Alasan Beli</div>
        <input className="input" value={f.reason} onChange={(e) => set("reason", e.target.value)} placeholder="Breakout MA200 dengan volume tinggi" />
      </div>
      <div className="flex gap-2 justify-end">
        <button className="btn" onClick={onCancel}>Batal</button>
        <button className="btn btn-active" onClick={submit} disabled={busy || !f.symbol}>
          {busy ? "Menyimpan…" : "Simpan"}
        </button>
      </div>
    </div>
  );
}
