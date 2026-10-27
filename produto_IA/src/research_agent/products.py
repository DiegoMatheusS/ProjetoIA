from ..catalog_specs import technical_attribute
"""Pesquisa de Produtos cuja ficha fica em metadados, com evidência por campo."""
from copy import deepcopy
from datetime import datetime, timezone
import re
import time

from ..catalog_content import technical_name, technical_description, plain_text
from ..enrichment.identity import build_identity, identity_is_strong
from ..enrichment.providers import ManufacturerProvider, IcecatProvider, GeizhalsProvider
from ..enrichment.quality import evidence_for_specs
from ..extractors.backend_schemas import SCHEMAS
from ..extractors.ml_specs import extract_specs
from ..extractors.dto_normalizer import normalize_specs_for_backend

_EXCLUDE = re.compile(r"pre[cç]o|price|frete|shipping|vendedor|seller|loja|store|garantia|warranty|pagamento|payment|parcel|avalia[cç]|rating|estoque|stock|disponibilidade|descri[cç]|description|hist[oó]ria|history|^url$", re.I)
_DANGEROUS = {"__proto__", "constructor", "prototype", "nome", "name", "marca", "brand", "modelo", "model", "mpn", "gtin", "ean"}


def _metadata_specs(payload):
    metadata = payload.get("metadados") if isinstance(payload.get("metadados"), dict) else {}
    found = metadata.get("especificacoesEncontradas")
    current = metadata.get("especificacoes")
    return {**(found if isinstance(found, dict) else {}), **(current if isinstance(current, dict) else {})}


def research_product_specs(*, category, payload, name=None, providers=None, time_budget_seconds=16):
    category = str(category or "").upper()
    schema = SCHEMAS.get(category)
    if not schema or schema[0] != "PRODUTO" or schema[1]:
        raise ValueError("Categoria não usa ficha em metadados")
    final = deepcopy(payload or {})
    final["nome"] = technical_name(final.get("nome") or name, final.get("marca"), final.get("modelo"), category)
    before = _metadata_specs(final)
    values, origins, conflicts, sources = {}, {}, {}, []
    identity = build_identity({"payloadParcialBackend": final})
    deadline = time.monotonic() + min(30, max(1, time_budget_seconds or 16))
    if identity_is_strong(identity):
        for provider in providers if providers is not None else [ManufacturerProvider(), IcecatProvider(), GeizhalsProvider()]:
            if time.monotonic() >= deadline:
                break
            if hasattr(provider, "supports") and not provider.supports(category, identity):
                continue
            provider.timeout = min(4, max(1, int(deadline-time.monotonic())))
            try:
                source = provider.collect(identity, category)
            except Exception:
                sources.append({"fonte": provider.name, "ok": False, "erro": "FONTE_INDISPONIVEL"})
                continue
            sources.append({"fonte": source.get("fonte") or provider.name, "url": source.get("url"), "ok": bool(source.get("ok"))})
            if not source.get("ok"):
                continue
            if schema[2]:
                found = normalize_specs_for_backend(category, extract_specs(category, source.get("attributes") or [], context_text=source.get("context_text") or ""))
                evidence = evidence_for_specs(category, source, found)
            else:
                found, evidence = {}, {}
                for row in (source.get("attributes") or [])[:200]:
                    if not isinstance(row, dict):
                        continue
                    key, value = plain_text(row.get("name")), plain_text(row.get("value_name"))
                    if not technical_attribute(key, value) or not key or not value or len(key)>80 or len(value)>180 or _EXCLUDE.search(key) or key.casefold() in _DANGEROUS:
                        continue
                    found[key] = value
                    evidence[key] = {"url": row.get("source_url") or source.get("url"), "fonte": source.get("fonte") or provider.name, "trecho": f"{key}: {value}", "valor": value, "metodo": "EXTRACAO_DETERMINISTICA"}
            for field, value in found.items():
                origin = evidence.get(field)
                if before.get(field) not in (None, "", []) or value in (None, "", []) or not origin or not origin.get("url") or not origin.get("trecho"):
                    continue
                if field in values and values[field] != value:
                    conflicts[field] = {"campo": field, "valores": [values[field], value]}
                    origins.pop(field, None)
                elif field not in conflicts:
                    values[field] = value
                    origins[field] = {**origin, "evidenciaCampoConfirmada": True, "coletadoEm": datetime.now(timezone.utc).isoformat()}
    accepted = {field: values[field] for field in origins}
    merged = {**before, **accepted}
    metadata = final.get("metadados") if isinstance(final.get("metadados"), dict) else {}
    final["metadados"] = {**metadata, "especificacoesEncontradas": merged}
    description = technical_description(category, final.get("nome"), merged, final.get("descricao"))
    return {"categoria": category, "nome": final.get("nome"), "payload": final,
            "descricaoTecnica": description, "utilizado": bool(accepted), "provedor": "PROJETO_IA",
            "somentePreencheLacunas": True, "camposPreenchidos": list(accepted),
            "origemPorCampo": origins, "conflitos": list(conflicts.values()), "fontesConsultadas": sources,
            "motivo": "ESPECIFICACOES_DOCUMENTADAS" if accepted else "SEM_DADOS_CONFIRMADOS" if identity_is_strong(identity) else "MODELO_EXATO_NAO_IDENTIFICADO"}
