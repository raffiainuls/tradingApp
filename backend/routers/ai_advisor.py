"""Tab 5 — AI Advisor: analisa single-stock & rekomendasi harian via Hermes Agent.

Generate MANUAL saja (tombol), sinkron (bukan BackgroundTasks) -- ini satu kali
panggilan Hermes per request (bukan batch 15 saham seperti AI Picks), jadi cukup
tunggu satu response langsung dengan timeout longgar di sisi frontend.
"""
import re
from fastapi import APIRouter, HTTPException, Query

import ai_advisor

router = APIRouter(prefix="/api")
_SAFE_ID = re.compile(r"^[A-Z0-9^.]{1,20}$")


@router.post("/ai-advisor/analysis")
def analyze(symbol: str = Query(...)):
    sym = symbol.upper()
    if not _SAFE_ID.match(sym):
        raise HTTPException(400, "symbol invalid")
    result = ai_advisor.analyze_symbol(sym)
    if result.get("error") == "no_data":
        raise HTTPException(404, f"Tidak ada data untuk {sym}")
    if result.get("error") == "insufficient_data":
        raise HTTPException(422, f"Data {sym} belum cukup untuk dianalisa (kurang dari 30 bar)")
    return result


@router.post("/ai-advisor/daily-picks")
def daily_picks():
    return ai_advisor.daily_recommendations()
