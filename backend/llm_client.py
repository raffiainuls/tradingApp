"""Klien LLM generik (OpenAI-compatible chat completions).

Arahkan ke Ollama/vLLM/LocalAI/LM Studio self-hosted via LLM_BASE_URL.
Kosongkan LLM_BASE_URL untuk menonaktifkan (AI Picks tetap jalan, rule-based only).

Catatan: berbeda dari Hermes CLI subprocess (docs/hermes-integration.md, dipakai
Tab 5 AI Advisor). Di sini LLM_BASE_URL kosong = no-op instan TANPA network call.
"""
import httpx

import config


def call_llm(prompt: str, system: str | None = None) -> str | None:
    if not config.LLM_BASE_URL:
        return None          # tidak dikonfigurasi -> no-op instan, tanpa network call
    try:
        headers = {"Authorization": f"Bearer {config.LLM_API_KEY}"} if config.LLM_API_KEY else {}
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        resp = httpx.post(
            f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
            json={"model": config.LLM_MODEL, "messages": messages,
                  "temperature": 0.4, "max_tokens": config.LLM_MAX_TOKENS},
            headers=headers, timeout=config.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content.strip() or None
    except Exception as e:
        print(f"[!] LLM call failed: {e}", flush=True)
        return None          # NEVER raise — 1 saham gagal tidak boleh gagalkan batch
