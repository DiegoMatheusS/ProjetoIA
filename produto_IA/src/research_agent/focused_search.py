from __future__ import annotations

from collections.abc import Iterable

from .query_builder import build_focus_terms, build_focused_queries


class FocusedSearchResolver:
    """Proxy conservador que tenta uma consulta focada antes da consulta genérica.

    O resolver real continua responsável por rede, cache, limites e browser fallback.
    Este proxy só altera a consulta usada para localizar a página mais útil para as
    lacunas atuais da ficha.
    """

    def __init__(
        self,
        delegate,
        *,
        category: str,
        missing_fields: Iterable[str],
        max_focused_queries: int = 1,
    ):
        self._delegate = delegate
        self.category = str(category or "").strip().upper()
        self.missing_fields = tuple(str(x) for x in (missing_fields or ()) if x)
        self.focus_terms = build_focus_terms(self.category, self.missing_fields)
        self.max_focused_queries = max(1, min(2, int(max_focused_queries)))
        self.queries_executed: list[str] = []

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    @property
    def allow_browser_fallback(self):
        return getattr(self._delegate, "allow_browser_fallback", False)

    @allow_browser_fallback.setter
    def allow_browser_fallback(self, value):
        setattr(self._delegate, "allow_browser_fallback", value)

    @property
    def timeout(self):
        return getattr(self._delegate, "timeout", 15)

    @timeout.setter
    def timeout(self, value):
        setattr(self._delegate, "timeout", value)

    @property
    def last_status(self):
        return getattr(self._delegate, "last_status", None)

    def _queries(self, base_query: str) -> tuple[str, ...]:
        return build_focused_queries(
            base_query,
            self.category,
            self.missing_fields,
            max_queries=self.max_focused_queries,
        )

    def _record(self, query: str):
        value = str(query or "").strip()
        if value and value not in self.queries_executed:
            self.queries_executed.append(value)

    def first_result(self, query, allowed_domains):
        queries = self._queries(query)
        for candidate_query in queries:
            self._record(candidate_query)
            result = self._delegate.first_result(candidate_query, allowed_domains)
            if result:
                return result
        return None

    def results(self, query, allowed_domains, limit=10):
        queries = self._queries(query)
        merged = []
        seen = set()
        for candidate_query in queries:
            self._record(candidate_query)
            items = self._delegate.results(candidate_query, allowed_domains, limit=limit)
            for item in items or []:
                url = str((item or {}).get("url") or "").strip()
                key = url.split("#", 1)[0].rstrip("/").casefold()
                if not url or key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                if len(merged) >= max(1, int(limit)):
                    return merged
            # Uma consulta focada que já encontrou candidatos é preferida à busca
            # genérica; evita duplicar chamadas e aumentar a latência do botão.
            if merged and candidate_query != queries[-1]:
                return merged
        return merged[: max(1, int(limit))]
