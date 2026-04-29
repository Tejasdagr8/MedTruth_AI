"""
LLM text generation with provider fallback.

Primary: Groq (fast, cheap)
Fallback: Gemini → Anthropic → Ollama (local)
"""

import logging
import os
import re
import time
from typing import Callable, Optional

import anthropic
import httpx

from src.observability import request_id as _request_id

logger = logging.getLogger(__name__)


CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
MAX_RETRIES = int(os.getenv("LLM_PROVIDER_MAX_RETRIES", "2"))
RETRY_BACKOFF_SECONDS = float(os.getenv("LLM_PROVIDER_RETRY_BACKOFF_SECONDS", "0.4"))
_LAST_SUCCESS_PROVIDER: Optional[str] = None
_PROVIDER_METRICS: dict[str, dict[str, float | int]] = {
    "anthropic": {"success": 0, "failure": 0, "last_latency_ms": 0.0, "last_fail_latency_ms": 0.0},
    "groq":      {"success": 0, "failure": 0, "last_latency_ms": 0.0, "last_fail_latency_ms": 0.0},
    "gemini":    {"success": 0, "failure": 0, "last_latency_ms": 0.0, "last_fail_latency_ms": 0.0},
    "ollama":    {"success": 0, "failure": 0, "last_latency_ms": 0.0, "last_fail_latency_ms": 0.0},
}


class ProviderFallbackError(RuntimeError):
    def __init__(self, message: str, attempts: list[str]):
        super().__init__(message)
        self.attempts = attempts


def get_provider_metrics() -> dict[str, dict[str, float | int | None]]:
    """Return a snapshot with derived fields (total_calls, success_rate) computed server-side."""
    result: dict[str, dict[str, float | int | None]] = {}
    for name, m in _PROVIDER_METRICS.items():
        total = int(m["success"]) + int(m["failure"])
        result[name] = {
            **m,
            "total_calls":   total,
            "success_rate":  round(int(m["success"]) / total, 3) if total > 0 else None,
        }
    return result


def _generate_with_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text_blocks = [block.text for block in message.content if getattr(block, "text", None)]
    return "\n".join(text_blocks).strip()


def _generate_with_groq(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(GROQ_BASE_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("Groq returned no choices")
    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Groq returned empty content")
    return content.strip()


def _generate_with_gemini(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    candidate_models = [
        GEMINI_MODEL,
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro-latest",
    ]
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": max_tokens,
        },
    }

    last_error: Optional[Exception] = None
    with httpx.Client(timeout=60.0) as client:
        for model in candidate_models:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={gemini_api_key}"
            )
            try:
                response = client.post(url, json=payload, headers={"Content-Type": "application/json"})
                response.raise_for_status()
                data = response.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"Gemini model {model} returned no candidates")
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
                if not text.strip():
                    raise RuntimeError(f"Gemini model {model} returned empty content")
                return text.strip()
            except Exception as exc:
                last_error = exc
                continue

    raise RuntimeError(f"Gemini fallback failed across candidate models: {last_error}")


def _generate_with_ollama(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    prompt = f"{system_prompt}\n\nUSER:\n{user_prompt}"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.2,
        },
    }
    with httpx.Client(timeout=90.0) as client:
        response = client.post(url, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        data = response.json()
    text = data.get("response", "")
    if not text or not text.strip():
        raise RuntimeError("Ollama returned empty response")
    return text.strip()


def _sanitize_error_message(msg: str) -> str:
    # Mask API keys in URLs or inline tokens.
    msg = re.sub(r"key=[^&\s]+", "key=***", msg)
    msg = re.sub(r"(sk-[a-zA-Z0-9_-]+)", "***", msg)
    msg = re.sub(r"(gsk_[a-zA-Z0-9]+)", "***", msg)
    msg = re.sub(r"(AIza[0-9A-Za-z\-_]+)", "***", msg)
    return msg


def _is_retryable_error(exc: Exception) -> bool:
    """Only retry transient errors — skip auth/config failures immediately."""
    msg = str(exc).lower()
    return any(k in msg for k in ["timeout", "rate limit", "429", "500", "503", "connection"])


def generate_text_with_fallback(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
) -> tuple[str, str, list[str]]:
    """
    Generate text using Groq first, then Gemini, Anthropic, and local Ollama.
    Returns (text, provider_name, attempted).
    """
    global _LAST_SUCCESS_PROVIDER

    provider_errors: dict[str, Optional[Exception]] = {
        "groq": None,
        "gemini": None,
        "anthropic": None,
        "ollama": None,
    }
    attempted: list[str] = []

    # Groq is cheapest and fastest; Anthropic is last resort.
    providers: list[tuple[str, Callable[[str, str, int], str], bool]] = [
        ("groq", _generate_with_groq, bool(os.getenv("GROQ_API_KEY"))),
        ("gemini", _generate_with_gemini, bool(os.getenv("GEMINI_API_KEY"))),
        ("anthropic", _generate_with_anthropic, bool(os.getenv("ANTHROPIC_API_KEY"))),
        ("ollama", _generate_with_ollama, os.getenv("OLLAMA_ENABLED", "false").lower() == "true"),
    ]

    # Stickiness: prioritize last successful provider only if its failure count is low.
    if _LAST_SUCCESS_PROVIDER and int(_PROVIDER_METRICS[_LAST_SUCCESS_PROVIDER]["failure"]) < 3:
        providers.sort(key=lambda p: 0 if p[0] == _LAST_SUCCESS_PROVIDER else 1)

    for provider_name, fn, available in providers:
        if not available:
            provider_errors[provider_name] = RuntimeError(f"{provider_name} provider not configured")
            continue

        last_exc: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            attempted.append(f"{provider_name}:attempt{attempt}")
            started = time.perf_counter()
            try:
                text = fn(system_prompt, user_prompt, max_tokens)
                if not text.strip():
                    raise RuntimeError(f"{provider_name} returned empty content")
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                _PROVIDER_METRICS[provider_name]["success"] += 1
                _PROVIDER_METRICS[provider_name]["last_latency_ms"] = latency_ms
                _LAST_SUCCESS_PROVIDER = provider_name
                rid = _request_id.get()
                if attempt > 1:
                    logger.info(
                        "[LLM] rid=%s provider=%s attempt=%d/%d status=success latency_ms=%.0f",
                        rid, provider_name, attempt, MAX_RETRIES, latency_ms,
                    )
                return text, provider_name, attempted
            except Exception as exc:
                last_exc = exc
                fail_latency_ms = round((time.perf_counter() - started) * 1000, 2)
                # Record latency of every attempt — not just successes — so the
                # admin health tab can distinguish "fast fail" from "slow timeout".
                _PROVIDER_METRICS[provider_name]["last_fail_latency_ms"] = fail_latency_ms
                rid = _request_id.get()
                sanitized = _sanitize_error_message(str(exc))
                if attempt < MAX_RETRIES and _is_retryable_error(exc):
                    logger.warning(
                        "[LLM] rid=%s provider=%s attempt=%d/%d status=retry reason=%s delay_s=%.1f",
                        rid, provider_name, attempt, MAX_RETRIES, sanitized, RETRY_BACKOFF_SECONDS * attempt,
                    )
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                else:
                    logger.warning(
                        "[LLM] rid=%s provider=%s attempt=%d/%d status=failed reason=%s latency_ms=%.0f",
                        rid, provider_name, attempt, MAX_RETRIES, sanitized, fail_latency_ms,
                    )
                    break
        provider_errors[provider_name] = last_exc
        _PROVIDER_METRICS[provider_name]["failure"] += 1

    error_parts = [
        f"{name} failed: {err}" for name, err in provider_errors.items() if err is not None
    ]
    raise ProviderFallbackError(
        _sanitize_error_message(". ".join(error_parts) + f". Attempts: {attempted}"),
        attempts=attempted,
    )
