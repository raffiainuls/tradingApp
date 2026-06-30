"""Tab 2 — Trading Analyst API: symbols, history+indicators, quotes, WebSocket."""
import re
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query

import config
import db
import indicators as ind
import realtime

router = APIRouter()

_SAFE_ID = re.compile(r"^[A-Z0-9^.]{1,20}$")


def _validate_symbol(s: str) -> str:
    s = s.upper()
    if not _SAFE_ID.match(s):
        raise HTTPException(400, f"Invalid symbol: {s!r}")
    return s


def _validate_interval(iv: str) -> str:
    if iv not in config.VALID_INTERVALS:
        raise HTTPException(400, f"Invalid interval. Use: {sorted(config.VALID_INTERVALS)}")
    return iv


@router.get("/api/symbols")
def symbols():
    syms = db.list_symbols()
    stocks = [s for s in syms if s["type"] != "index"]
    idx = [s for s in syms if s["type"] == "index"]
    return {"stocks": stocks, "indices": idx, "count": len(syms)}


@router.get("/api/history/{symbol}")
def history(
    symbol: str,
    interval: str = Query("1d"),
    limit: int = Query(400, ge=10, le=1000),
    indicators: str | None = Query(None),
):
    sym = _validate_symbol(symbol)
    iv = _validate_interval(interval)
    df = db.fetch_ohlcv(sym, iv, limit=limit)
    if df.empty:
        return {"symbol": sym, "interval": iv, "candles": [], "indicators": {}, "signals": {}}

    candles = [
        {"time": int(ts.timestamp()), "open": round(float(r.open), 2), "high": round(float(r.high), 2),
         "low": round(float(r.low), 2), "close": round(float(r.close), 2), "volume": float(r.volume or 0)}
        for ts, r in df.iterrows()
    ]
    want = [x.strip() for x in indicators.split(",") if x.strip()] if indicators else None
    return {
        "symbol": sym, "interval": iv, "candles": candles,
        "indicators": ind.compute_all(df, want=want, interval=iv),
        "signals": ind.latest_signals(df, interval=iv),
    }


@router.get("/api/quote/{symbol}")
def quote(symbol: str, interval: str = Query("1d")):
    sym = _validate_symbol(symbol)
    iv = _validate_interval(interval)
    df = db.fetch_ohlcv(sym, iv, limit=2)
    if df.empty:
        return {"symbol": sym, "interval": iv, "price": None}
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    change = float(last.close) - float(prev.close)
    pct = (change / float(prev.close) * 100) if prev.close else 0.0
    return {"symbol": sym, "interval": iv, "price": round(float(last.close), 2),
            "open": round(float(last.open), 2), "high": round(float(last.high), 2),
            "low": round(float(last.low), 2), "volume": float(last.volume or 0),
            "change": round(change, 2), "change_pct": round(pct, 2)}


@router.get("/api/quotes")
def quotes(interval: str = Query("1d")):
    iv = _validate_interval(interval)
    return db.fetch_quotes(iv)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    realtime.connected_ws.add(ws)
    await ws.send_json({"type": "snapshot", "data": realtime.latest_quote})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        realtime.connected_ws.discard(ws)
    except Exception:
        realtime.connected_ws.discard(ws)
