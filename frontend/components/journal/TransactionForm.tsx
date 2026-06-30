"use client";
import { useState } from "react";

const SECTORS = ["Banking", "Telco", "Consumer", "Energy", "Mining", "Healthcare",
  "Industrials", "Basic Materials", "Retail", "Tech", "Property", "Lainnya"];

export default function TransactionForm({
  onSubmit, onCancel,
}: { onSubmit: (data: any) => Promise<void>; onCancel: () => void }) {
  const [f, setF] = useState({
    symbol: "", side: "BUY", trade_date: new Date().toISOString().slice(0, 10),
    price: 0, lots: 1, fee: 0, sector: "Banking", tags: "", notes: "",
  });
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    setBusy(true);
    try {
      await onSubmit({
        symbol: f.symbol.toUpperCase(), side: f.side, trade_date: f.trade_date,
        price: Number(f.price), lots: Number(f.lots), fee: Number(f.fee),
        sector: f.sector,
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
          <input className="input" value={f.symbol} onChange={(e) => set("symbol", e.target.value)} placeholder="BBRI" />
        </div>
        <div>
          <div className="label mb-1">Aksi</div>
          <select className="input" value={f.side} onChange={(e) => set("side", e.target.value)}>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </div>
        <div>
          <div className="label mb-1">Tanggal</div>
          <input className="input" type="date" value={f.trade_date} onChange={(e) => set("trade_date", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Harga</div>
          <input className="input" type="number" value={f.price} onChange={(e) => set("price", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Lot</div>
          <input className="input" type="number" value={f.lots} onChange={(e) => set("lots", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Fee (Rp)</div>
          <input className="input" type="number" value={f.fee} onChange={(e) => set("fee", e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Sektor</div>
          <select className="input" value={f.sector} onChange={(e) => set("sector", e.target.value)}>
            {SECTORS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <div className="label mb-1">Tags</div>
          <input className="input" value={f.tags} onChange={(e) => set("tags", e.target.value)} placeholder="swing" />
        </div>
      </div>
      <div>
        <div className="label mb-1">Catatan (mis. kesalahan trading)</div>
        <input className="input" value={f.notes} onChange={(e) => set("notes", e.target.value)} placeholder="FOMO entry, salah timing" />
      </div>
      <div className="flex gap-2 justify-end">
        <button className="btn" onClick={onCancel}>Batal</button>
        <button className="btn btn-active" onClick={submit} disabled={busy || !f.symbol}>
          {busy ? "Menyimpan…" : "Catat Transaksi"}
        </button>
      </div>
    </div>
  );
}
