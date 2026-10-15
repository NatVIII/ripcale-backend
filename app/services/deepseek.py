"""DeepSeek chat-completions client (F65).

A thin `httpx` wrapper over `https://api.deepseek.com/chat/completions`
(OpenAI-compatible), used by the LLM event pipeline. No third-party SDK — the
project already depends on `httpx`.
"""
#region: imports
import logging
import time

import httpx

from app.config import settings
#endregion


logger = logging.getLogger(__name__)

BASE_URL = "https://api.deepseek.com"
TIMEOUT = 60.0
_MAX_ATTEMPTS = 3


#region: errors
class DeepSeekError(RuntimeError):
    """Base error for the DeepSeek client."""


class DeepSeekPermanent(DeepSeekError):
    """Auth/request errors (401/403/400) or missing key — retrying won't help."""


class DeepSeekTransient(DeepSeekError):
    """429/5xx/network — retried, then raised."""
#endregion


def chat(
    messages: list[dict],
    *,
    json_mode: bool = False,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    thinking: bool = True,
) -> str:
    """Send a chat completion and return the assistant text (raises on failure)."""
    if not settings.deepseek_key:
        raise DeepSeekPermanent("RIPCALE_DEEPSEEK_KEY is not set")

    payload: dict = {
        "model": settings.deepseek_model,
        "messages": messages,
        "stream": False,
        "thinking": {"type": "enabled" if thinking else "disabled"},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature

    headers = {
        "Authorization": f"Bearer {settings.deepseek_key}",
        "Content-Type": "application/json",
    }

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = httpx.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=TIMEOUT)
        except httpx.RequestError as exc:
            last_exc = exc  # network — transient
        else:
            if resp.status_code in (429, 500, 502, 503, 504):
                last_exc = RuntimeError(f"DeepSeek {resp.status_code}: {resp.text[:300]}")
            elif resp.status_code >= 400:
                raise DeepSeekPermanent(f"DeepSeek {resp.status_code}: {resp.text[:300]}")
            else:
                return resp.json()["choices"][0]["message"]["content"]
        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(1.0 * (attempt + 1))

    raise DeepSeekTransient(f"DeepSeek request failed: {last_exc}")
#endregion
