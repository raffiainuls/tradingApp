"""Klien HTTP ke Hermes Advisor Bridge (scripts/hermes_advisor_bridge.py, jalan di
HOST). Dipakai Tab 5 AI Advisor untuk minta narasi dari Hermes Agent (`bro_analysis`).

Beda mekanisme dari llm_client.py (Tab 3 AI Picks, HTTP ke gateway LLM cloud/self-hosted
generik). Di sini tujuannya spesifik Hermes CLI subprocess, dijembatani lewat HTTP krn
backend jalan di Docker sedangkan `bro_analysis` cuma ada di PATH host.
"""
import httpx

import config


def ask_hermes(prompt: str) -> str | None:
    try:
        resp = httpx.post(
            f"{config.HERMES_BRIDGE_URL.rstrip('/')}/advise",
            json={"prompt": prompt, "timeout": config.HERMES_BRIDGE_TIMEOUT_SECONDS},
            timeout=config.HERMES_BRIDGE_TIMEOUT_SECONDS + 10,
        )
        resp.raise_for_status()
        text = (resp.json() or {}).get("text")
        return text.strip() if text else None
    except Exception as e:
        print(f"[!] Hermes bridge call failed: {e}", flush=True)
        return None          # NEVER raise — tanpa narasi AI, data teknikal tetap tampil
