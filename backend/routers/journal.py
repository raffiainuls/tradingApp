"""Tab 1 — Trading Journal API: portfolio, transaksi, analitik (P&L, win rate, equity curve)."""
from collections import defaultdict, deque
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db

router = APIRouter(prefix="/api/journal")

LOT_SIZE = 100  # 1 lot = 100 lembar


# ── Schemas ───────────────────────────────────────────────────────────────────
class PositionIn(BaseModel):
    symbol: str = Field(..., max_length=20)
    lots: int = Field(..., gt=0)
    avg_price: float = Field(..., gt=0)
    buy_date: date
    target_price: Optional[float] = None
    cutloss_price: Optional[float] = None
    sector: Optional[str] = None
    reason: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class TransactionIn(BaseModel):
    symbol: str = Field(..., max_length=20)
    side: str = Field(..., pattern="^(BUY|SELL)$")
    trade_date: date
    price: float = Field(..., gt=0)
    lots: int = Field(..., gt=0)
    fee: float = Field(0, ge=0)
    sector: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _current_price(symbol: str) -> Optional[float]:
    try:
        d = db.fetch_ohlcv(symbol.upper(), "1d", limit=1)
        if not d.empty:
            return float(d.iloc[-1].close)
    except Exception:
        pass
    return None


# ── Positions (Portofolio aktif) ──────────────────────────────────────────────
@router.get("/positions")
def list_positions():
    with db.pg_cursor() as cur:
        cur.execute("SELECT * FROM positions ORDER BY created_at DESC")
        rows = cur.fetchall()

    out = []
    tot_cost = tot_value = 0.0
    for r in rows:
        avg = float(r["avg_price"])
        lots = int(r["lots"])
        cost = avg * lots * LOT_SIZE
        cur_price = _current_price(r["symbol"])
        if cur_price is None:
            cur_price = avg
        mkt = cur_price * lots * LOT_SIZE
        upnl = mkt - cost
        out.append({
            **r,
            "avg_price": avg,
            "current_price": round(cur_price, 2),
            "cost_basis": round(cost, 2),
            "market_value": round(mkt, 2),
            "unrealized_pnl": round(upnl, 2),
            "return_pct": round((upnl / cost * 100) if cost else 0, 2),
        })
        tot_cost += cost
        tot_value += mkt

    summary = {
        "total_cost": round(tot_cost, 2),
        "total_value": round(tot_value, 2),
        "total_pnl": round(tot_value - tot_cost, 2),
        "total_return_pct": round(((tot_value - tot_cost) / tot_cost * 100) if tot_cost else 0, 2),
        "position_count": len(out),
    }

    # alokasi per sektor
    by_sector = defaultdict(float)
    for p in out:
        by_sector[p.get("sector") or "Lainnya"] += p["market_value"]
    allocation = [
        {"sector": s, "value": round(v, 2), "pct": round((v / tot_value * 100) if tot_value else 0, 2)}
        for s, v in sorted(by_sector.items(), key=lambda x: -x[1])
    ]

    return {"positions": out, "summary": summary, "allocation": allocation}


@router.post("/positions", status_code=201)
def create_position(p: PositionIn):
    with db.pg_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO positions
               (symbol, lots, avg_price, buy_date, target_price, cutloss_price, sector, reason, tags, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (p.symbol.upper(), p.lots, p.avg_price, p.buy_date, p.target_price,
             p.cutloss_price, p.sector, p.reason, p.tags, p.notes),
        )
        return cur.fetchone()


@router.put("/positions/{pid}")
def update_position(pid: int, p: PositionIn):
    with db.pg_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE positions SET
               symbol=%s, lots=%s, avg_price=%s, buy_date=%s, target_price=%s,
               cutloss_price=%s, sector=%s, reason=%s, tags=%s, notes=%s
               WHERE id=%s RETURNING *""",
            (p.symbol.upper(), p.lots, p.avg_price, p.buy_date, p.target_price,
             p.cutloss_price, p.sector, p.reason, p.tags, p.notes, pid),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Position not found")
        return row


@router.delete("/positions/{pid}", status_code=204)
def delete_position(pid: int):
    with db.pg_cursor(commit=True) as cur:
        cur.execute("DELETE FROM positions WHERE id=%s", (pid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Position not found")


# ── Transactions (Log historis) ───────────────────────────────────────────────
@router.get("/transactions")
def list_transactions():
    with db.pg_cursor() as cur:
        cur.execute("SELECT * FROM transactions ORDER BY trade_date DESC, id DESC")
        return {"transactions": cur.fetchall()}


@router.post("/transactions", status_code=201)
def create_transaction(t: TransactionIn):
    with db.pg_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO transactions
               (symbol, side, trade_date, price, lots, fee, sector, tags, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (t.symbol.upper(), t.side, t.trade_date, t.price, t.lots, t.fee,
             t.sector, t.tags, t.notes),
        )
        return cur.fetchone()


@router.delete("/transactions/{tid}", status_code=204)
def delete_transaction(tid: int):
    with db.pg_cursor(commit=True) as cur:
        cur.execute("DELETE FROM transactions WHERE id=%s", (tid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Transaction not found")


# ── Analitik (FIFO matching) ──────────────────────────────────────────────────
@router.get("/analytics")
def analytics():
    """Win rate, holding period, best/worst trade, equity curve, realized P&L per emiten."""
    with db.pg_cursor() as cur:
        cur.execute("SELECT * FROM transactions ORDER BY trade_date ASC, id ASC")
        txs = cur.fetchall()

    lots_q: dict[str, deque] = defaultdict(deque)   # FIFO buy lots per symbol
    closed_trades = []

    for t in txs:
        sym = t["symbol"]
        lots = int(t["lots"])
        price = float(t["price"])
        fee = float(t["fee"] or 0)
        fee_per_lot = fee / lots if lots else 0

        if t["side"] == "BUY":
            lots_q[sym].append({
                "date": t["trade_date"], "price": price,
                "lots": lots, "fee_per_lot": fee_per_lot, "sector": t["sector"],
            })
        else:  # SELL → match FIFO
            remaining = lots
            sell_fee_per_lot = fee_per_lot
            while remaining > 0 and lots_q[sym]:
                buy = lots_q[sym][0]
                matched = min(remaining, buy["lots"])
                gross = (price - buy["price"]) * matched * LOT_SIZE
                fees = (buy["fee_per_lot"] + sell_fee_per_lot) * matched
                pnl = gross - fees
                hold_days = (t["trade_date"] - buy["date"]).days
                closed_trades.append({
                    "symbol": sym,
                    "sector": t["sector"] or buy["sector"],
                    "buy_date": buy["date"].isoformat(),
                    "sell_date": t["trade_date"].isoformat(),
                    "buy_price": round(buy["price"], 2),
                    "sell_price": round(price, 2),
                    "lots": matched,
                    "pnl": round(pnl, 2),
                    "return_pct": round((price - buy["price"]) / buy["price"] * 100, 2),
                    "holding_days": hold_days,
                })
                buy["lots"] -= matched
                remaining -= matched
                if buy["lots"] == 0:
                    lots_q[sym].popleft()

    # Agregasi
    n = len(closed_trades)
    wins = [c for c in closed_trades if c["pnl"] > 0]
    losses = [c for c in closed_trades if c["pnl"] < 0]
    total_pnl = sum(c["pnl"] for c in closed_trades)

    by_symbol = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    for c in closed_trades:
        b = by_symbol[c["symbol"]]
        b["pnl"] += c["pnl"]
        b["trades"] += 1
        if c["pnl"] > 0:
            b["wins"] += 1
    per_symbol = [
        {"symbol": s, "pnl": round(v["pnl"], 2), "trades": v["trades"],
         "win_rate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0}
        for s, v in sorted(by_symbol.items(), key=lambda x: -x[1]["pnl"])
    ]

    # Equity curve (kumulatif realized P&L per tanggal jual)
    curve, running = [], 0.0
    for c in sorted(closed_trades, key=lambda x: x["sell_date"]):
        running += c["pnl"]
        curve.append({"date": c["sell_date"], "equity": round(running, 2)})

    best = max(closed_trades, key=lambda c: c["pnl"]) if closed_trades else None
    worst = min(closed_trades, key=lambda c: c["pnl"]) if closed_trades else None
    avg_hold = round(sum(c["holding_days"] for c in closed_trades) / n, 1) if n else 0

    return {
        "stats": {
            "total_realized_pnl": round(total_pnl, 2),
            "total_trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / n * 100, 1) if n else 0,
            "avg_win": round(sum(c["pnl"] for c in wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(c["pnl"] for c in losses) / len(losses), 2) if losses else 0,
            "profit_factor": round(
                sum(c["pnl"] for c in wins) / abs(sum(c["pnl"] for c in losses)), 2
            ) if losses and sum(c["pnl"] for c in losses) != 0 else None,
            "avg_holding_days": avg_hold,
            "best_trade": best,
            "worst_trade": worst,
        },
        "per_symbol": per_symbol,
        "equity_curve": curve,
        "closed_trades": sorted(closed_trades, key=lambda x: x["sell_date"], reverse=True),
    }
