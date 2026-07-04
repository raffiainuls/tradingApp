"""Tab 4 — Screener: daily-picks rule-based (composite scoring) seluruh universe IDX."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

import config
import screener

router = APIRouter(prefix="/api")


def _vi(iv: str) -> str:
    if iv not in config.VALID_INTERVALS:
        raise HTTPException(400, "interval invalid")
    return iv


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
