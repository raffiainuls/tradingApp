"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Position, PortfolioSummary, Allocation, Transaction, Analytics } from "@/lib/types";
import { fmtPrice, fmtPct, fmtMoney, colorOf } from "@/lib/format";
import PositionForm from "@/components/journal/PositionForm";
import TransactionForm from "@/components/journal/TransactionForm";
import EquityCurve from "@/components/journal/EquityCurve";

type Tab = "porto" | "tx" | "analytics";

export default function JournalPage() {
  const [tab, setTab] = useState<Tab>("porto");
  const [positions, setPositions] = useState<Position[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [allocation, setAllocation] = useState<Allocation[]>([]);
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);

  const [showPosForm, setShowPosForm] = useState(false);
  const [editPos, setEditPos] = useState<Position | null>(null);
  const [showTxForm, setShowTxForm] = useState(false);

  const loadPositions = () =>
    api.positions().then((d) => { setPositions(d.positions); setSummary(d.summary); setAllocation(d.allocation); }).catch(() => {});
  const loadTx = () => api.transactions().then((d) => setTxs(d.transactions)).catch(() => {});
  const loadAnalytics = () => api.analytics().then(setAnalytics).catch(() => {});

  useEffect(() => { loadPositions(); loadTx(); loadAnalytics(); }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Trading Journal</h1>
          <p className="text-xs text-dim mt-0.5">Portofolio aktif, log transaksi & analisis performa</p>
        </div>
        <div className="flex gap-1">
          {([["porto", "Portofolio"], ["tx", "Transaksi"], ["analytics", "Analisis"]] as [Tab, string][]).map(
            ([k, l]) => (
              <button key={k} onClick={() => setTab(k)} className={`btn ${tab === k ? "btn-active" : ""}`}>{l}</button>
            )
          )}
        </div>
      </div>

      {/* ── Summary cards (selalu tampil) ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 px-6 py-4">
        <Stat label="Nilai Portofolio" value={fmtMoney(summary?.total_value)} />
        <Stat label="Modal" value={fmtMoney(summary?.total_cost)} />
        <Stat
          label="Unrealized P&L"
          value={fmtMoney(summary?.total_pnl)}
          sub={fmtPct(summary?.total_return_pct)}
          color={colorOf(summary?.total_pnl)}
        />
        <Stat
          label="Realized P&L"
          value={fmtMoney(analytics?.stats.total_realized_pnl)}
          sub={analytics ? `${analytics.stats.total_trades} trade` : ""}
          color={colorOf(analytics?.stats.total_realized_pnl)}
        />
      </div>

      <div className="px-6 pb-8">
        {tab === "porto" && (
          <PortfolioTab
            positions={positions}
            allocation={allocation}
            showForm={showPosForm}
            editPos={editPos}
            onAdd={() => { setEditPos(null); setShowPosForm(true); }}
            onEdit={(p: Position) => { setEditPos(p); setShowPosForm(true); }}
            onCancel={() => { setShowPosForm(false); setEditPos(null); }}
            onSubmit={async (data: any) => {
              if (editPos) await api.updatePosition(editPos.id, data);
              else await api.createPosition(data);
              setShowPosForm(false); setEditPos(null); loadPositions();
            }}
            onDelete={async (id: number) => { await api.deletePosition(id); loadPositions(); }}
          />
        )}

        {tab === "tx" && (
          <TxTab
            txs={txs}
            showForm={showTxForm}
            onAdd={() => setShowTxForm(true)}
            onCancel={() => setShowTxForm(false)}
            onSubmit={async (data: any) => { await api.createTransaction(data); setShowTxForm(false); loadTx(); loadAnalytics(); }}
            onDelete={async (id: number) => { await api.deleteTransaction(id); loadTx(); loadAnalytics(); }}
          />
        )}

        {tab === "analytics" && <AnalyticsTab a={analytics} />}
      </div>
    </div>
  );
}

// ── Stat card ──
function Stat({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className={`text-xl font-bold mt-1 font-mono ${color || ""}`}>{value}</div>
      {sub && <div className={`text-xs mt-0.5 font-mono ${color || "text-dim"}`}>{sub}</div>}
    </div>
  );
}

// ── Portfolio tab ──
function PortfolioTab({ positions, allocation, showForm, editPos, onAdd, onEdit, onCancel, onSubmit, onDelete }: any) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-dim">Posisi Aktif ({positions.length})</h2>
        {!showForm && <button className="btn btn-active" onClick={onAdd}>+ Tambah Posisi</button>}
      </div>

      {showForm && <PositionForm initial={editPos || undefined} onSubmit={onSubmit} onCancel={onCancel} />}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-dim text-xs border-b border-border">
              {["Kode", "Lot", "Avg", "Harga", "Nilai", "P&L", "Return", "Target", "CL", "Sektor", ""].map((h) => (
                <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((p: Position) => (
              <tr key={p.id} className="border-b border-border/40 hover:bg-panel2">
                <td className="px-3 py-2 font-semibold">{p.symbol}</td>
                <td className="px-3 py-2 font-mono">{p.lots}</td>
                <td className="px-3 py-2 font-mono">{fmtPrice(p.avg_price)}</td>
                <td className="px-3 py-2 font-mono">{fmtPrice(p.current_price)}</td>
                <td className="px-3 py-2 font-mono">{fmtMoney(p.market_value)}</td>
                <td className={`px-3 py-2 font-mono ${colorOf(p.unrealized_pnl)}`}>{fmtMoney(p.unrealized_pnl)}</td>
                <td className={`px-3 py-2 font-mono ${colorOf(p.return_pct)}`}>{fmtPct(p.return_pct)}</td>
                <td className="px-3 py-2 font-mono text-dim">{p.target_price ? fmtPrice(p.target_price) : "–"}</td>
                <td className="px-3 py-2 font-mono text-dim">{p.cutloss_price ? fmtPrice(p.cutloss_price) : "–"}</td>
                <td className="px-3 py-2 text-xs text-dim">{p.sector || "–"}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <button className="text-xs text-accent hover:underline mr-2" onClick={() => onEdit(p)}>edit</button>
                  <button className="text-xs text-down hover:underline" onClick={() => onDelete(p.id)}>hapus</button>
                </td>
              </tr>
            ))}
            {!positions.length && (
              <tr><td colSpan={11} className="px-3 py-8 text-center text-dim text-sm">Belum ada posisi. Klik "Tambah Posisi".</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {allocation.length > 0 && (
        <div className="card p-4">
          <div className="label mb-3">Alokasi per Sektor</div>
          <div className="space-y-2">
            {allocation.map((a: Allocation) => (
              <div key={a.sector}>
                <div className="flex justify-between text-xs mb-1">
                  <span>{a.sector}</span>
                  <span className="text-dim font-mono">{fmtMoney(a.value)} · {a.pct}%</span>
                </div>
                <div className="h-2 bg-bg rounded-full overflow-hidden">
                  <div className="h-full bg-accent" style={{ width: `${a.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Transactions tab ──
function TxTab({ txs, showForm, onAdd, onCancel, onSubmit, onDelete }: any) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-dim">Log Transaksi ({txs.length})</h2>
        {!showForm && <button className="btn btn-active" onClick={onAdd}>+ Catat Transaksi</button>}
      </div>

      {showForm && <TransactionForm onSubmit={onSubmit} onCancel={onCancel} />}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-dim text-xs border-b border-border">
              {["Tanggal", "Kode", "Aksi", "Harga", "Lot", "Nilai", "Fee", "Catatan", ""].map((h) => (
                <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {txs.map((t: Transaction) => (
              <tr key={t.id} className="border-b border-border/40 hover:bg-panel2">
                <td className="px-3 py-2 font-mono text-dim">{t.trade_date}</td>
                <td className="px-3 py-2 font-semibold">{t.symbol}</td>
                <td className="px-3 py-2">
                  <span className={`chip ${t.side === "BUY" ? "text-up border-up/40" : "text-down border-down/40"}`}>{t.side}</span>
                </td>
                <td className="px-3 py-2 font-mono">{fmtPrice(t.price)}</td>
                <td className="px-3 py-2 font-mono">{t.lots}</td>
                <td className="px-3 py-2 font-mono">{fmtMoney(t.price * t.lots * 100)}</td>
                <td className="px-3 py-2 font-mono text-dim">{fmtMoney(t.fee)}</td>
                <td className="px-3 py-2 text-xs text-dim max-w-[200px] truncate">{t.notes || "–"}</td>
                <td className="px-3 py-2">
                  <button className="text-xs text-down hover:underline" onClick={() => onDelete(t.id)}>hapus</button>
                </td>
              </tr>
            ))}
            {!txs.length && (
              <tr><td colSpan={9} className="px-3 py-8 text-center text-dim text-sm">Belum ada transaksi.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Analytics tab ──
function AnalyticsTab({ a }: { a: Analytics | null }) {
  if (!a) return <div className="text-sm text-dim">Memuat analitik…</div>;
  const s = a.stats;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Win Rate" value={`${s.win_rate}%`} sub={`${s.wins}W / ${s.losses}L`} color={s.win_rate >= 50 ? "text-up" : "text-down"} />
        <Stat label="Profit Factor" value={s.profit_factor != null ? s.profit_factor.toFixed(2) : "–"} color={s.profit_factor && s.profit_factor >= 1 ? "text-up" : "text-down"} />
        <Stat label="Avg Win / Loss" value={fmtMoney(s.avg_win)} sub={fmtMoney(s.avg_loss)} />
        <Stat label="Avg Holding" value={`${s.avg_holding_days} hari`} />
      </div>

      <div className="card p-4">
        <div className="label mb-2">Equity Curve (Realized)</div>
        <EquityCurve data={a.equity_curve} />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-4">
          <div className="label mb-2">Best / Worst Trade</div>
          {s.best_trade && (
            <div className="flex justify-between text-sm py-1.5 border-b border-border/40">
              <span>🏆 {s.best_trade.symbol} <span className="text-dim text-xs">({s.best_trade.holding_days}h)</span></span>
              <span className="text-up font-mono">{fmtMoney(s.best_trade.pnl)} · {fmtPct(s.best_trade.return_pct)}</span>
            </div>
          )}
          {s.worst_trade && (
            <div className="flex justify-between text-sm py-1.5">
              <span>💀 {s.worst_trade.symbol} <span className="text-dim text-xs">({s.worst_trade.holding_days}h)</span></span>
              <span className="text-down font-mono">{fmtMoney(s.worst_trade.pnl)} · {fmtPct(s.worst_trade.return_pct)}</span>
            </div>
          )}
          {!s.best_trade && <div className="text-xs text-dim">Belum ada trade tertutup.</div>}
        </div>

        <div className="card p-4">
          <div className="label mb-2">P&L per Emiten</div>
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {a.per_symbol.map((p) => (
              <div key={p.symbol} className="flex justify-between text-sm">
                <span>{p.symbol} <span className="text-dim text-xs">({p.trades}x · {p.win_rate}%)</span></span>
                <span className={`font-mono ${colorOf(p.pnl)}`}>{fmtMoney(p.pnl)}</span>
              </div>
            ))}
            {!a.per_symbol.length && <div className="text-xs text-dim">–</div>}
          </div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <div className="label px-4 pt-3">Riwayat Trade Tertutup (FIFO)</div>
        <table className="w-full text-sm mt-2">
          <thead>
            <tr className="text-left text-dim text-xs border-b border-border">
              {["Kode", "Beli", "Jual", "Hrg Beli", "Hrg Jual", "Lot", "P&L", "Return", "Hari"].map((h) => (
                <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {a.closed_trades.map((c, i) => (
              <tr key={i} className="border-b border-border/40 hover:bg-panel2">
                <td className="px-3 py-2 font-semibold">{c.symbol}</td>
                <td className="px-3 py-2 font-mono text-dim">{c.buy_date}</td>
                <td className="px-3 py-2 font-mono text-dim">{c.sell_date}</td>
                <td className="px-3 py-2 font-mono">{fmtPrice(c.buy_price)}</td>
                <td className="px-3 py-2 font-mono">{fmtPrice(c.sell_price)}</td>
                <td className="px-3 py-2 font-mono">{c.lots}</td>
                <td className={`px-3 py-2 font-mono ${colorOf(c.pnl)}`}>{fmtMoney(c.pnl)}</td>
                <td className={`px-3 py-2 font-mono ${colorOf(c.return_pct)}`}>{fmtPct(c.return_pct)}</td>
                <td className="px-3 py-2 font-mono text-dim">{c.holding_days}</td>
              </tr>
            ))}
            {!a.closed_trades.length && (
              <tr><td colSpan={9} className="px-3 py-8 text-center text-dim text-sm">Belum ada trade tertutup.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
