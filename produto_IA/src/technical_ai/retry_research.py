from __future__ import annotations

import os
import time
from copy import deepcopy
from typing import Any

from .iterative_research import IterativeAIResult, run_iterative_external_research as _run_base
from .providers import TechnicalAIProviderError


_RETRYABLE_CODES = {"TIMEOUT_PROVEDOR", "PROVEDOR_INDISPONIVEL"}


def _retry_budget_seconds() -> float:
    try:
        value = float(os.getenv("TECH_RESEARCH_OPENAI_TRANSIENT_RETRY_BUDGET_SECONDS", "16"))
    except (TypeError, ValueError):
        value = 16.0
    return min(20.0, max(6.0, value))


def _dedupe(items: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for item in items:
        marker = repr(item)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


class _SingleApiRetryProvider:
    """Permite somente uma nova chamada real à OpenAI dentro do retry.

    Se o fluxo iterativo pedir uma segunda rodada após a chamada de recuperação,
    reutilizamos a mesma resposta em memória. Assim um timeout inicial nunca vira
    três chamadas pagas à API.
    """

    def __init__(self, provider, total_budget_seconds: float):
        self.provider = provider
        self.deadline = time.monotonic() + total_budget_seconds
        self.cached_response = None

    def enrich_with_budget(self, prompt: str, *, budget_seconds: float):
        if self.cached_response is not None:
            return self.cached_response

        remaining = self.deadline - time.monotonic()
        if remaining < 3.0:
            raise TechnicalAIProviderError(
                "ORCAMENTO_TEMPO_ESGOTADO",
                "Orçamento da tentativa de recuperação OpenAI esgotado",
                status_code=504,
                transient=True,
            )

        applied = min(float(budget_seconds), remaining)
        method = getattr(self.provider, "enrich_with_budget", None)
        if callable(method):
            response = method(prompt, budget_seconds=applied)
        else:
            response = self.provider.enrich(prompt)
        self.cached_response = response
        return response

    def enrich(self, prompt: str):
        return self.enrich_with_budget(prompt, budget_seconds=_retry_budget_seconds())


def _merge_results(first: IterativeAIResult, retry: IterativeAIResult) -> IterativeAIResult:
    retry_rounds = []
    offset = len(first.rounds)
    for index, item in enumerate(retry.rounds, start=1):
        row = deepcopy(item)
        row["numero"] = offset + index
        row["tentativaExterna"] = "RETRY_TRANSIENTE"
        retry_rounds.append(row)

    parsed = dict(first.parsed_specs or {})
    parsed.update(retry.parsed_specs or {})
    provenance = dict(first.provenance or {})
    provenance.update(retry.provenance or {})

    return IterativeAIResult(
        payload=retry.payload,
        filled_fields=_dedupe(list(first.filled_fields or []) + list(retry.filled_fields or [])),
        parsed_specs=parsed,
        conflicts=_dedupe(list(first.conflicts or []) + list(retry.conflicts or [])),
        rejected=_dedupe(list(first.rejected or []) + list(retry.rejected or [])),
        sources=_dedupe(list(first.sources or []) + list(retry.sources or [])),
        provenance=provenance,
        rounds=list(first.rounds or []) + retry_rounds,
        first_prompt=first.first_prompt or retry.first_prompt,
        first_requested_fields=list(first.first_requested_fields or retry.first_requested_fields or []),
        provider=retry.provider or first.provider,
        model=retry.model or first.model,
        provider_error=retry.provider_error,
    )


def run_iterative_external_research_with_retry(
    *,
    provider,
    category: str,
    name: str | None,
    payload: dict[str, Any],
    local_info: dict[str, Any] | None = None,
) -> IterativeAIResult:
    """Repete uma vez apenas falhas transitórias sem descartar pesquisa local.

    Não repete falta de crédito, chave inválida, modelo indisponível ou erro de
    payload. O retry possui orçamento próprio curto e no máximo uma nova chamada
    real ao provedor.
    """
    first = _run_base(
        provider=provider,
        category=category,
        name=name,
        payload=payload,
        local_info=local_info,
    )

    error = first.provider_error
    if (
        error is None
        or first.filled_fields
        or error.code not in _RETRYABLE_CODES
        or not bool(error.transient)
    ):
        return first

    retry_provider = _SingleApiRetryProvider(provider, _retry_budget_seconds())
    retry = _run_base(
        provider=retry_provider,
        category=category,
        name=name,
        payload=first.payload,
        local_info=local_info,
    )
    return _merge_results(first, retry)
