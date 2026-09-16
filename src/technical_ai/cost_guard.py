from __future__ import annotations

import os
from typing import Any

from ..utils.rate_limiter import JsonDiskCache
from .providers import TechnicalAIResponse


_CACHE_NAMESPACE = "technical-ai-openai-response-v1"
_CACHE_URL = "technical-ai://openai-response"


def _enabled() -> bool:
    return os.getenv("TECH_RESEARCH_OPENAI_RESPONSE_CACHE_ENABLED", "true").strip().casefold() in {
        "1",
        "true",
        "sim",
        "yes",
        "on",
    }


def _ttl_seconds() -> int:
    try:
        value = int(os.getenv("TECH_RESEARCH_OPENAI_RESPONSE_CACHE_TTL_SECONDS", "21600"))
    except (TypeError, ValueError):
        value = 21600
    return min(7 * 86400, max(300, value))


def _provider_name(provider: Any) -> str:
    return str(getattr(provider, "name", "") or "").strip().upper()


def _params(provider: Any, prompt: str, identity_key: str) -> dict[str, Any]:
    return {
        "provider": _provider_name(provider),
        "model": str(getattr(provider, "model", "") or "").strip(),
        "webSearch": bool(getattr(provider, "web_search", False)),
        "identity": str(identity_key or "").strip(),
        "prompt": str(prompt or "").strip(),
    }


class ExternalAIResponseCache:
    """Cache curto da resposta paga, separado do cache de pesquisa local.

    So reutiliza resposta quando ha identidade forte do hardware. A chave inclui
    categoria/identidade, modelo OpenAI, uso de Web Search e o prompt completo.
    Assim uma falha de cadastro pode ser repetida sem nova cobranca, sem misturar
    variantes ou revisoes diferentes.
    """

    def __init__(self, cache: JsonDiskCache | None = None):
        self.cache = cache or JsonDiskCache()

    def get(
        self,
        provider: Any,
        prompt: str,
        *,
        identity_key: str | None,
    ) -> TechnicalAIResponse | None:
        clean_identity = str(identity_key or "").strip()
        if not _enabled() or _provider_name(provider) != "OPENAI" or not clean_identity:
            return None
        clean_prompt = str(prompt or "").strip()
        if not clean_prompt:
            return None
        cached = self.cache.get(
            _CACHE_URL,
            params=_params(provider, clean_prompt, clean_identity),
            namespace=_CACHE_NAMESPACE,
            ttl_seconds=_ttl_seconds(),
        )
        if not isinstance(cached, dict):
            return None
        text = str(cached.get("text") or "").strip()
        if not text:
            return None
        sources = [item for item in (cached.get("sources") or []) if isinstance(item, dict)]
        return TechnicalAIResponse(
            provider=str(cached.get("provider") or "OPENAI"),
            model=str(cached.get("model") or getattr(provider, "model", "")),
            text=text,
            sources=sources,
            raw_metadata={
                "cacheHit": True,
                "cacheTipo": "RESPOSTA_OPENAI_PAGA",
                "cacheIdentity": clean_identity,
            },
        )

    def set(
        self,
        provider: Any,
        prompt: str,
        response: TechnicalAIResponse,
        *,
        identity_key: str | None,
    ) -> None:
        clean_identity = str(identity_key or "").strip()
        if not _enabled() or _provider_name(provider) != "OPENAI" or not clean_identity:
            return
        clean_prompt = str(prompt or "").strip()
        text = str(getattr(response, "text", "") or "").strip()
        if not clean_prompt or not text:
            return
        self.cache.set(
            _CACHE_URL,
            {
                "provider": str(getattr(response, "provider", "OPENAI") or "OPENAI"),
                "model": str(getattr(response, "model", "") or ""),
                "text": text,
                "sources": [
                    item for item in (getattr(response, "sources", None) or []) if isinstance(item, dict)
                ],
            },
            params=_params(provider, clean_prompt, clean_identity),
            namespace=_CACHE_NAMESPACE,
        )
