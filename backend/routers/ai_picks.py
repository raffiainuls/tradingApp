"""Tab 3 — AI Picks: top-N bullish + reasoning LLM (generate MANUAL via tombol).

GET /api/ai-picks         → batch terbaru (read-only; TIDAK memicu generate)
GET /api/ai-picks/status  → status generate (untuk polling frontend)
POST /api/ai-picks/generate → satu-satunya pemicu generate (tombol "Generate/Refresh")
"""
from fastapi import APIRouter, BackgroundTasks

import ai_picks

router = APIRouter(prefix="/api")


@router.get("/ai-picks")
def get_ai_picks():
    return {"picks": ai_picks.latest_batch()}


@router.get("/ai-picks/history")
def get_ai_picks_history():
    return {"batches": ai_picks.history_batches()}


@router.get("/ai-picks/status")
def get_ai_picks_status():
    return {"generating": ai_picks.is_generating(), "last_generated_at": ai_picks.last_generated_at()}


@router.post("/ai-picks/generate")
def trigger_ai_picks(bg: BackgroundTasks):
    if ai_picks.is_generating():
        return {"started": False, "reason": "already_generating"}
    bg.add_task(ai_picks.generate)
    return {"started": True}
