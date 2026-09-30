"""
One place that talks to the language model.

Two backends are supported and can be switched with LLM_PROVIDER in .env:

  auto    (default) use the paid API when an API key is set and working,
          otherwise fall back to the local Ollama model automatically.
  api     API only. Errors are reported, no fallback.
  ollama  local Ollama only. The API is never contacted.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_API_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_OLLAMA_MODEL = "llama3:8b-instruct-q4_K_M"
DEFAULT_OLLAMA_URL = "http://localhost:11434/v1/chat/completions"


class LLMError(Exception):
    """Raised when no backend could answer."""


def _settings():
    return {
        "provider": os.getenv("LLM_PROVIDER", "auto").strip().lower(),
        "api_key": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        "api_model": os.getenv("ANTHROPIC_MODEL", DEFAULT_API_MODEL),
        "ollama_model": os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        "ollama_url": os.getenv("OLLAMA_ENDPOINT", DEFAULT_OLLAMA_URL),
    }


def _call_api(cfg, system, user, temperature, max_tokens, timeout):
    res = requests.post(
        API_URL,
        headers={
            "x-api-key": cfg["api_key"],
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": cfg["api_model"],
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    res.raise_for_status()
    blocks = res.json().get("content", [])
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def _call_ollama(cfg, system, user, temperature, max_tokens, timeout, json_mode):
    payload = {
        "model": cfg["ollama_model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    res = requests.post(cfg["ollama_url"], json=payload, timeout=timeout)
    res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"].strip()


def chat(system, user, temperature=0.2, max_tokens=700, timeout=60, json_mode=False):
    """
    Send one system + user message and return (text, backend_name).
    backend_name is "api" or "ollama", so callers can log which one answered.
    """
    cfg = _settings()
    provider = cfg["provider"]
    api_usable = bool(cfg["api_key"])
    errors = []

    if provider in ("auto", "api"):
        if api_usable:
            try:
                return _call_api(cfg, system, user, temperature, max_tokens, timeout), "api"
            except Exception as e:
                errors.append(f"API: {e}")
                if provider == "api":
                    raise LLMError("; ".join(errors))
        elif provider == "api":
            raise LLMError("LLM_PROVIDER=api but ANTHROPIC_API_KEY is not set.")

    if provider in ("auto", "ollama"):
        try:
            return _call_ollama(cfg, system, user, temperature, max_tokens, timeout, json_mode), "ollama"
        except Exception as e:
            errors.append(f"Ollama: {e}")

    if not errors:
        errors.append(f"Unknown LLM_PROVIDER '{provider}' (use auto, api or ollama).")
    raise LLMError("; ".join(errors))


def status():
    """Non-secret summary of the current setup, for the /api/status endpoint."""
    cfg = _settings()
    return {
        "provider_setting": cfg["provider"],
        "api_key_set": bool(cfg["api_key"]),
        "api_model": cfg["api_model"],
        "ollama_model": cfg["ollama_model"],
    }
