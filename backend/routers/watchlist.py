"""Tab 3 — Watchlist: manual CRUD + screener/daily-picks (rule-based scoring)."""
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import config
import db
import screener

router = APIRouter(prefix="/api")
_SAFE_ID = re.compile(r"^[A-Z0-9^.]{1,20}$")


class WatchIn(BaseModel):
    symbol: str = Field(..., max_length=20)
    note: Optional[str] = None


def _vi(iv: str) -> str:
    if iv not in config.VALID_INTERVALS:
        raise HTTPException(400, "interval invalid")
    return iv


# ── Manual watchlist ──
@router.get("/watchlist")
def list_watchlist():
    with db.pg_cursor() as cur:
        cur.execute("SELECT * FROM watchlist ORDER BY created_at DESC")
        rows = cur.fetchall()
    # enrich: skor (dari cache screener 1d) + harga/perubahan
    scores = {r["symbol"]: r for r in screener.compute_universe("1d")}
    out = []
    for w in rows:
        s = scores.get(w["symbol"], {})
        out.append({**w, "price": s.get("close"), "change_pct": s.get("change_pct"),
                    "score": s.get("score"), "verdict": s.get("verdict"), "rsi": s.get("rsi")})
    return {"watchlist": out}


@router.post("/watchlist", status_code=201)
def add_watchlist(w: WatchIn):
    sym = w.symbol.upper()
    if not _SAFE_ID.match(sym):
        raise HTTPException(400, "symbol invalid")
    with db.pg_cursor(commit=True) as cur:
        cur.execute("INSERT INTO watchlist (symbol, note) VALUES (%s,%s) RETURNING *", (sym, w.note))
        return cur.fetchone()


@router.delete("/watchlist/{wid}", status_code=204)
def del_watchlist(wid: int):
    with db.pg_cursor(commit=True) as cur:
        cur.execute("DELETE FROM watchlist WHERE id=%s", (wid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "not found")


# ── Screener / daily picks ──
@router.get("/screener")
def screen(
    interval: str = Query("1d"),
    limit: int = Query(50, ge=1, le=200),
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_vol_ratio: Optional[float] = None,
    rsi_below: Optional[float] = None,
    rsi_above: Optional[float] = None,
    above_ma200: bool = False,
    verdict: Optional[str] = None,
    exclude_special: bool = True,
):
    iv = _vi(interval)
    filters = {
        "limit": limit, "min_score": min_score, "max_score": max_score,
        "min_price": min_price, "max_price": max_price, "min_vol_ratio": min_vol_ratio,
        "rsi_below": rsi_below, "rsi_above": rsi_above, "above_ma200": above_ma200,
        "verdict": verdict, "exclude_special": exclude_special,
    }
    results = screener.screen(iv, filters)
    return {"interval": iv, "count": len(results), "results": results}


@router.get("/screener/presets")
def presets():
    """Preset screener siap-pakai."""
    return {"presets": [
        {"key": "strong_buy", "label": "Strong Buy", "params": {"min_score": 50, "above_ma200": True}},
        {"key": "oversold_bounce", "label": "Oversold + Uptrend", "params": {"rsi_below": 35, "above_ma200": True}},
        {"key": "breakout_vol", "label": "Breakout Volume", "params": {"min_vol_ratio": 2.0, "min_score": 20}},
        {"key": "momentum", "label": "Momentum Kuat", "params": {"min_score": 40}},
        {"key": "oversold", "label": "Oversold (RSI<30)", "params": {"rsi_below": 30}},
    ]}
