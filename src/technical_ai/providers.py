"""Providers de IA externa para enriquecimento técnico de Hardware.

O provider é deliberadamente pequeno: envia um prompt e devolve texto bruto.
Toda interpretação, normalização e validação continuam dentro da Produto IA.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


logger = logging.getLogger("uvicorn.error")


@dataclass
class TechnicalAIResponse:
    provider: str
    model: str
    text: str
    sources: list[dict[str, str]]
    raw_metadata: dict[str, Any] | None = None


class TechnicalAIProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 502,
        transient: bool = False,
        provider_status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.transient = transient
        self.provider_status_code = provider_status_code


class TechnicalAIProvider:
    name = "EXTERNO"

    @property
    def configured(self) -> bool:
        return False

    def enrich(self, prompt: str) -> TechnicalAIResponse:  # pragma: no cover - interface
        raise NotImplementedError


class GeminiProvider(TechnicalAIProvider):
    """Gemini API via REST, com Google Search opcional para pesquisa técnica.

    Não usa SDK adicional para manter o serviço leve; ``requests`` já faz parte
    do Projeto IA. A chave é enviada somente em ``x-goog-api-key``.
    """

    name = "GEMINI"
    api_base = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, *, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = (os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash")
        self.enabled = os.getenv("GEMINI_ENABLED", "true").strip().casefold() in {"1", "true", "sim", "yes", "on"}
        self.google_search = os.getenv("GEMINI_GOOGLE_SEARCH", "true").strip().casefold() in {"1", "true", "sim", "yes", "on"}
        try:
            self.timeout = max(5.0, float(os.getenv("GEMINI_TIMEOUT_SECONDS", "45")))
        except ValueError:
            self.timeout = 45.0
        try:
            self.max_retries = min(3, max(0, int(os.getenv("GEMINI_MAX_RETRIES", "1"))))
        except ValueError:
            self.max_retries = 1
        try:
            self.temperature = min(1.0, max(0.0, float(os.getenv("GEMINI_TEMPERATURE", "0.1"))))
        except ValueError:
            self.temperature = 0.1
        try:
            self.max_output_tokens = min(8192, max(512, int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "4096"))))
        except ValueError:
            self.max_output_tokens = 4096

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key)

    def _endpoint(self) -> str:
        # model é configurável, mas não deve conseguir alterar host/rota.
        model = quote(self.model.strip(), safe="-._")
        return f"{self.api_base}/models/{model}:generateContent"

    def _request_body(self, prompt: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,
            },
        }
        if self.google_search:
            body["tools"] = [{"google_search": {}}]
        return body

    @staticmethod
    def _response_text(data: dict[str, Any]) -> str:
        for candidate in data.get("candidates") or []:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            chunks: list[str] = []
            for part in parts:
                if isinstance(part, dict) and not part.get("thought") and isinstance(part.get("text"), str):
                    text = part["text"].strip()
                    if text:
                        chunks.append(text)
            if chunks:
                return "\n".join(chunks).strip()
        return ""

    @staticmethod
    def _sources(data: dict[str, Any]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for candidate in data.get("candidates") or []:
            metadata = candidate.get("groundingMetadata") or {}
            for chunk in metadata.get("groundingChunks") or []:
                if not isinstance(chunk, dict):
                    continue
                web = chunk.get("web") or {}
                uri = str(web.get("uri") or "").strip()
                title = str(web.get("title") or "").strip()
                if uri and uri not in seen:
                    seen.add(uri)
                    out.append({"url": uri, "titulo": title})
        return out[:20]

    @staticmethod
    def _provider_error(response: requests.Response) -> TechnicalAIProviderError:
        status = int(response.status_code)
        detail = ""
        try:
            payload = response.json()
            detail = str((payload.get("error") or {}).get("message") or "").strip()
        except Exception:
            detail = (response.text or "").strip()[:500]

        if status in {401, 403}:
            return TechnicalAIProviderError(
                "CHAVE_INVALIDA",
                detail or "Chave Gemini inválida ou sem permissão",
                status_code=502,
                provider_status_code=status,
            )
        if status == 429:
            return TechnicalAIProviderError(
                "LIMITE_PROVEDOR",
                detail or "Limite do Gemini atingido",
                status_code=503,
                transient=True,
                provider_status_code=status,
            )
        if status in {408, 504}:
            return TechnicalAIProviderError(
                "TIMEOUT_PROVEDOR",
                detail or "Timeout no Gemini",
                status_code=504,
                transient=True,
                provider_status_code=status,
            )
        if status == 404:
            return TechnicalAIProviderError(
                "MODELO_INDISPONIVEL",
                "Modelo Gemini não disponível. Confira GEMINI_MODEL e o acesso da chave a esse modelo.",
                status_code=502,
                provider_status_code=status,
            )
        if status == 400:
            return TechnicalAIProviderError(
                "RESPOSTA_INVALIDA",
                detail or "Requisição rejeitada pelo Gemini",
                status_code=502,
                provider_status_code=status,
            )
        if status >= 500:
            return TechnicalAIProviderError(
                "PROVEDOR_INDISPONIVEL",
                detail or "Gemini indisponível",
                status_code=503,
                transient=True,
                provider_status_code=status,
            )
        return TechnicalAIProviderError(
            "RESPOSTA_INVALIDA",
            detail or f"Gemini retornou HTTP {status}",
            status_code=502,
            provider_status_code=status,
        )

    def _log_failure(self, error: TechnicalAIProviderError) -> None:
        # Nunca registrar chave ou prompt. Apenas estado seguro de configuração
        # e a mensagem devolvida pelo provedor, limitada a uma linha curta.
        safe_message = " ".join(str(error.message or "").split())[:1200]
        logger.error(
            "IA técnica Gemini falhou: codigo=%s status_http=%s status_provedor=%s "
            "transitorio=%s modelo=%s habilitado=%s api_key_configurada=%s "
            "google_search=%s mensagem=%s",
            error.code,
            error.status_code,
            error.provider_status_code,
            error.transient,
            self.model,
            self.enabled,
            bool(self.api_key),
            self.google_search,
            safe_message,
        )

    def enrich(self, prompt: str) -> TechnicalAIResponse:
        try:
            return self._enrich(prompt)
        except TechnicalAIProviderError as exc:
            self._log_failure(exc)
            raise

    def _enrich(self, prompt: str) -> TechnicalAIResponse:
        if not self.enabled:
            raise TechnicalAIProviderError("PROVEDOR_NAO_CONFIGURADO", "Provider Gemini está desabilitado", status_code=503)
        if not self.api_key:
            raise TechnicalAIProviderError("PROVEDOR_NAO_CONFIGURADO", "GEMINI_API_KEY não configurada", status_code=503)
        prompt = str(prompt or "").strip()
        if not prompt:
            raise TechnicalAIProviderError("PAYLOAD_INVALIDO", "Prompt técnico vazio", status_code=400)

        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = self._request_body(prompt)
        last_error: TechnicalAIProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(self._endpoint(), headers=headers, json=body, timeout=self.timeout)
            except requests.Timeout as exc:
                last_error = TechnicalAIProviderError("TIMEOUT_PROVEDOR", "Timeout ao consultar Gemini", status_code=504, transient=True)
                if attempt < self.max_retries:
                    time.sleep(min(2.0, 0.35 * (2 ** attempt)))
                    continue
                raise last_error from exc
            except requests.RequestException as exc:
                last_error = TechnicalAIProviderError("PROVEDOR_INDISPONIVEL", "Falha de rede ao consultar Gemini", status_code=503, transient=True)
                if attempt < self.max_retries:
                    time.sleep(min(2.0, 0.35 * (2 ** attempt)))
                    continue
                raise last_error from exc

            if response.status_code >= 400:
                last_error = self._provider_error(response)
                if last_error.transient and attempt < self.max_retries:
                    time.sleep(min(2.0, 0.35 * (2 ** attempt)))
                    continue
                raise last_error

            try:
                data = response.json()
            except ValueError as exc:
                raise TechnicalAIProviderError("RESPOSTA_INVALIDA", "Gemini retornou JSON inválido", status_code=502) from exc

            if not isinstance(data, dict):
                raise TechnicalAIProviderError("RESPOSTA_INVALIDA", "Gemini retornou formato inesperado", status_code=502)
            candidates = data.get("candidates") or []
            if candidates and candidates[0].get("finishReason") == "MAX_TOKENS":
                raise TechnicalAIProviderError("RESPOSTA_TRUNCADA", "Resposta técnica interrompida pelo limite de tokens. A ficha foi preservada; ajuste GEMINI_MAX_OUTPUT_TOKENS.", status_code=502)
            text = self._response_text(data)
            if not text:
                raise TechnicalAIProviderError("RESPOSTA_VAZIA", "Gemini não retornou conteúdo técnico", status_code=502)
            return TechnicalAIResponse(
                provider=self.name,
                model=self.model,
                text=text,
                sources=self._sources(data),
                raw_metadata={"googleSearchAtivo": bool(self.google_search)},
            )

        raise last_error or TechnicalAIProviderError("PROVEDOR_INDISPONIVEL", "Falha ao consultar Gemini", status_code=503)


def get_technical_ai_provider(name: str | None = None) -> TechnicalAIProvider:
    selected = (name or os.getenv("IA_TECNICA_PROVIDER", "GEMINI") or "GEMINI").strip().upper()
    if selected == "GEMINI":
        return GeminiProvider()
    raise TechnicalAIProviderError("PROVEDOR_NAO_CONFIGURADO", f"Provider técnico não suportado: {selected}", status_code=400)