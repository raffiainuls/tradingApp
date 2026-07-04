"""Tab 3 — Watchlist: manual CRUD (enrich skor dari cache screener)."""
import re
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
import screener

router = APIRouter(prefix="/api")
_SAFE_ID = re.compile(r"^[A-Z0-9^.]{1,20}$")


class WatchIn(BaseModel):
    symbol: str = Field(..., max_length=20)
    note: Optional[str] = None


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
