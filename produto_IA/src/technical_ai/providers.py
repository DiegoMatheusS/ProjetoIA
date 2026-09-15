"""Providers de IA externa para enriquecimento técnico de Hardware.

A Produto IA continua responsável por coletar, normalizar e validar os dados.
O provider externo serve apenas como camada complementar para preencher lacunas.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

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


class OpenAIProvider(TechnicalAIProvider):
    """OpenAI Responses API com Web Search opcional.

    A chave fica somente no servidor em ``OPENAI_API_KEY``. O provider devolve
    texto bruto para o parser/normalizador já existente na Produto IA.
    """

    name = "OPENAI"
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, *, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = (os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna")
        self.enabled = os.getenv("OPENAI_ENABLED", "true").strip().casefold() in {
            "1", "true", "sim", "yes", "on"
        }
        self.web_search = os.getenv("OPENAI_WEB_SEARCH", "true").strip().casefold() in {
            "1", "true", "sim", "yes", "on"
        }
        try:
            self.timeout = max(5.0, float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45")))
        except ValueError:
            self.timeout = 45.0
        try:
            self.max_retries = min(3, max(0, int(os.getenv("OPENAI_MAX_RETRIES", "1"))))
        except ValueError:
            self.max_retries = 1
        try:
            self.max_output_tokens = min(
                16384,
                max(512, int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "4096"))),
            )
        except ValueError:
            self.max_output_tokens = 4096

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key)

    def _request_body(self, prompt: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }
        if self.web_search:
            body["tools"] = [{"type": "web_search"}]
        return body

    @staticmethod
    def _response_text(data: dict[str, Any]) -> str:
        top_level = data.get("output_text")
        if isinstance(top_level, str) and top_level.strip():
            return top_level.strip()

        chunks: list[str] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    text = part["text"].strip()
                    if text:
                        chunks.append(text)
        return "\n".join(chunks).strip()

    @staticmethod
    def _sources(data: dict[str, Any]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                for annotation in part.get("annotations") or []:
                    if not isinstance(annotation, dict):
                        continue
                    url = str(annotation.get("url") or "").strip()
                    title = str(annotation.get("title") or "").strip()
                    if url and url not in seen:
                        seen.add(url)
                        out.append({"url": url, "titulo": title})
        return out[:20]

    @staticmethod
    def _provider_error(response: requests.Response) -> TechnicalAIProviderError:
        status = int(response.status_code)
        detail = ""
        try:
            payload = response.json()
            error = payload.get("error") or {}
            detail = str(error.get("message") or "").strip()
        except Exception:
            detail = (response.text or "").strip()[:500]

        if status in {401, 403}:
            return TechnicalAIProviderError(
                "CHAVE_INVALIDA",
                detail or "Chave OpenAI inválida ou sem permissão",
                status_code=502,
                provider_status_code=status,
            )
        if status == 429:
            return TechnicalAIProviderError(
                "LIMITE_PROVEDOR",
                detail or "Limite da OpenAI atingido",
                status_code=503,
                transient=True,
                provider_status_code=status,
            )
        if status in {408, 504}:
            return TechnicalAIProviderError(
                "TIMEOUT_PROVEDOR",
                detail or "Timeout na OpenAI",
                status_code=504,
                transient=True,
                provider_status_code=status,
            )
        if status == 404:
            return TechnicalAIProviderError(
                "MODELO_INDISPONIVEL",
                detail or "Modelo OpenAI não disponível para esta chave/projeto",
                status_code=502,
                provider_status_code=status,
            )
        if status == 400:
            return TechnicalAIProviderError(
                "RESPOSTA_INVALIDA",
                detail or "Requisição rejeitada pela OpenAI",
                status_code=502,
                provider_status_code=status,
            )
        if status >= 500:
            return TechnicalAIProviderError(
                "PROVEDOR_INDISPONIVEL",
                detail or "OpenAI indisponível",
                status_code=503,
                transient=True,
                provider_status_code=status,
            )
        return TechnicalAIProviderError(
            "RESPOSTA_INVALIDA",
            detail or f"OpenAI retornou HTTP {status}",
            status_code=502,
            provider_status_code=status,
        )

    def _log_failure(self, error: TechnicalAIProviderError) -> None:
        safe_message = " ".join(str(error.message or "").split())[:1200]
        logger.error(
            "IA técnica OpenAI falhou: codigo=%s status_http=%s status_provedor=%s "
            "transitorio=%s modelo=%s habilitado=%s api_key_configurada=%s "
            "web_search=%s mensagem=%s",
            error.code,
            error.status_code,
            error.provider_status_code,
            error.transient,
            self.model,
            self.enabled,
            bool(self.api_key),
            self.web_search,
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
            raise TechnicalAIProviderError(
                "PROVEDOR_NAO_CONFIGURADO",
                "Provider OpenAI está desabilitado",
                status_code=503,
            )
        if not self.api_key:
            raise TechnicalAIProviderError(
                "PROVEDOR_NAO_CONFIGURADO",
                "OPENAI_API_KEY não configurada",
                status_code=503,
            )
        prompt = str(prompt or "").strip()
        if not prompt:
            raise TechnicalAIProviderError(
                "PAYLOAD_INVALIDO",
                "Prompt técnico vazio",
                status_code=400,
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = self._request_body(prompt)
        last_error: TechnicalAIProviderError | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    self.endpoint,
                    headers=headers,
                    json=body,
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                last_error = TechnicalAIProviderError(
                    "TIMEOUT_PROVEDOR",
                    "Timeout ao consultar OpenAI",
                    status_code=504,
                    transient=True,
                )
                if attempt < self.max_retries:
                    time.sleep(min(2.0, 0.35 * (2 ** attempt)))
                    continue
                raise last_error from exc
            except requests.RequestException as exc:
                last_error = TechnicalAIProviderError(
                    "PROVEDOR_INDISPONIVEL",
                    "Falha de rede ao consultar OpenAI",
                    status_code=503,
                    transient=True,
                )
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
                raise TechnicalAIProviderError(
                    "RESPOSTA_INVALIDA",
                    "OpenAI retornou JSON inválido",
                    status_code=502,
                ) from exc

            if not isinstance(data, dict):
                raise TechnicalAIProviderError(
                    "RESPOSTA_INVALIDA",
                    "OpenAI retornou formato inesperado",
                    status_code=502,
                )

            if data.get("status") in {"incomplete", "failed", "cancelled", "in_progress", "queued"}:
                raise TechnicalAIProviderError(
                    "RESPOSTA_INCOMPLETA", "Resposta da OpenAI interrompida ou ainda não concluída", status_code=502,
                )
            text = self._response_text(data)
            if not text:
                raise TechnicalAIProviderError(
                    "RESPOSTA_VAZIA",
                    "OpenAI não retornou conteúdo técnico",
                    status_code=502,
                )

            return TechnicalAIResponse(
                provider=self.name,
                model=self.model,
                text=text,
                sources=self._sources(data),
                raw_metadata={"webSearchAtivo": bool(self.web_search)},
            )

        raise last_error or TechnicalAIProviderError(
            "PROVEDOR_INDISPONIVEL",
            "Falha ao consultar OpenAI",
            status_code=503,
        )


def get_technical_ai_provider(name: str | None = None) -> TechnicalAIProvider:
    selected = (
        name
        or os.getenv("IA_TECNICA_PROVIDER", "OPENAI")
        or "OPENAI"
    ).strip().upper()

    # Compatibilidade durante o deploy: versões antigas do frontend ainda podem
    # enviar GEMINI. O tráfego é redirecionado internamente para OpenAI; nenhuma
    # chamada ao Gemini é realizada.
    if selected in {"OPENAI", "GEMINI"}:
        return OpenAIProvider()

    raise TechnicalAIProviderError(
        "PROVEDOR_NAO_CONFIGURADO",
        f"Provider técnico não suportado: {selected}",
        status_code=400,
    )
