"""AI Picks (Tab 3) — orkestrasi top-N bullish + reasoning LLM (batch, HTTP).

Mirip gaya screener.py. State generasi disimpan sebagai module-level global (pola
realtime.py — connected_ws/latest_quote); aman karena backend jalan 1 worker uvicorn.

Beda mekanisme dari Tab 5 AI Advisor (single-stock, Hermes CLI subprocess) — di sini
batch banyak saham via HTTP OpenAI-compatible (llm_client.call_llm).
Level entry/target/cutloss dihitung deterministik dari ATR, BUKAN dari LLM.
"""
import threading
import time
from datetime import datetime, timezone

import config
import db
import screener
from llm_client import call_llm

_lock = threading.Lock()
_generating = False
_last_generated_at: float | None = None


def is_generating() -> bool:
    return _generating


def last_generated_at() -> float | None:
    return _last_generated_at


def _pick_candidates(top_n: int) -> list[dict]:
    """Top-N bullish (BUY/STRONG BUY) by score desc, exclude papan Pemantauan Khusus."""
    rows = screener.compute_universe("1d")
    board_map = db.board_map()
    bullish = sorted(
        [r for r in rows if r["verdict"] in ("BUY", "STRONG BUY")],
        key=lambda r: r["score"], reverse=True,
    )
    out = []
    for r in bullish:
        info = board_map.get(r["symbol"], {})
        board = info.get("board") or ""
        if "Khusus" in board:
            continue
        out.append({**r, "board": board, "sector": r.get("sector") or info.get("sector")})
        if len(out) >= top_n:
            break
    return out


def _build_prompt(c: dict) -> str:
    return (
        f"Analisa saham {c['symbol']} (papan: {c.get('board') or '-'}). "
        f"Data teknikal: skor komposit {c['score']} (verdict {c['verdict']}), "
        f"RSI {c.get('rsi')}, MACD histogram {c.get('macd_hist')}, ADX {c.get('adx')}, "
        f"harga close {c['close']}. Beri reasoning singkat 2-3 kalimat dalam Bahasa "
        "Indonesia mengapa saham ini layak masuk watchlist hari ini, tanpa menyebut "
        "harga target/entry/cutloss spesifik (sudah dihitung sistem secara terpisah)."
    )


def _levels(close: float, atr: float | None) -> tuple[float, float, float]:
    a = atr if atr else close * 0.02     # fallback ~2% kalau ATR tidak ada
    return round(close, 2), round(close + 2 * a, 2), round(close - 1.5 * a, 2)


def generate(top_n: int | None = None):
    """Jalan via BackgroundTasks. Lock cegah generate paralel (TTL-check vs tombol manual)."""
    global _generating, _last_generated_at
    if not _lock.acquire(blocking=False):
        return
    _generating = True
    try:
        n = top_n or config.AI_PICKS_TOP_N
        candidates = _pick_candidates(n)
        batch_at = datetime.now(timezone.utc)
        rows = []
        for c in candidates:
            reasoning = call_llm(_build_prompt(c))
            entry, target, cutloss = _levels(c["close"], c.get("atr"))
            rows.append((c["symbol"], c.get("sector"), c["verdict"], c["score"],
                         c.get("rsi"), c.get("macd_hist"), c.get("adx"), c.get("atr"),
                         c["close"], entry, target, cutloss, reasoning, batch_at))
        with db.pg_cursor(commit=True) as cur:
            for r in rows:
                cur.execute("""INSERT INTO ai_picks
                    (symbol, sector, verdict, score, rsi, macd_hist, adx, atr,
                     close_price, entry_price, target_price, cutloss_price, reasoning, batch_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", r)
        _last_generated_at = time.time()
        print(f"[+] AI Picks batch generated: {len(rows)} symbols", flush=True)
    except Exception as e:
        print(f"[!] AI Picks generation failed: {e}", flush=True)
    finally:
        _generating = False
        _lock.release()


def latest_batch() -> list[dict]:
    with db.pg_cursor() as cur:
        cur.execute("""SELECT * FROM ai_picks
                        WHERE batch_at = (SELECT max(batch_at) FROM ai_picks)
                        ORDER BY score DESC""")
        return cur.fetchall()
