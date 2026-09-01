from copy import deepcopy
import os
import time

from .identity import build_identity, identity_is_strong
from .providers import (
    ManufacturerProvider, TechPowerUpProvider, PCKomboProvider, GeizhalsProvider,
    CPUWorldProvider, WikiChipProvider, CPUMonkeyProvider,
)
from ..extractors.backend_schemas import SCHEMAS, REQUIRED
from ..extractors.ml_specs import extract_specs


def _missing(value):
    return value in (None, "", [])


def _normalized_for_compare(value):
    if isinstance(value, list):
        return sorted(str(x).casefold() for x in value)
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def technical_missing_fields(result):
    category = (result or {}).get("categoriaDetectada")
    schema = SCHEMAS.get(category) if category else None
    if not schema or not schema[1]:
        return []
    expected = schema[2] or []
    specs = (result or {}).get("especificacoesEncontradas") or {}
    return [field for field in expected if _missing(specs.get(field))]


def technical_coverage(result):
    category = (result or {}).get("categoriaDetectada")
    schema = SCHEMAS.get(category) if category else None
    if not schema or not schema[2]:
        return 1.0
    expected = schema[2] or []
    specs = (result or {}).get("especificacoesEncontradas") or {}
    present = sum(1 for field in expected if not _missing(specs.get(field)))
    return present / max(1, len(expected))


def required_missing_fields(result):
    category = (result or {}).get("categoriaDetectada")
    if not category:
        return []
    specs = (result or {}).get("especificacoesEncontradas") or {}
    return [field for field in REQUIRED.get(category, []) if _missing(specs.get(field))]


def should_auto_enrich(result):
    """Enriquece automaticamente só quando a ficha está realmente incompleta.

    v14.12/v14.13 acionavam enriquecimento quando faltava qualquer campo esperado.
    Em produção isso podia abrir várias consultas externas para praticamente toda URL
    e segurar a única vaga de PRODUTO_IA_CONCURRENCY.

    v14.14 dispara automaticamente quando:
    - existe identidade forte; e
    - falta campo obrigatório OU a cobertura técnica está abaixo do limite.
    """
    if not identity_is_strong(build_identity(result or {})):
        return False
    if required_missing_fields(result):
        return True
    try:
        threshold = float(os.getenv("ENRICHMENT_AUTO_MIN_COVERAGE", "0.45"))
    except ValueError:
        threshold = 0.45
    threshold = min(1.0, max(0.0, threshold))
    return technical_coverage(result) < threshold


class TechnicalEnricher:
    """Complementa campos técnicos ausentes sem bloquear a coleta comercial.

    auto_mode=True é o modo usado quando o enriquecimento foi disparado por lacunas.
    Nesse modo:
    - consulta no máximo algumas fontes relevantes;
    - usa timeouts menores;
    - não abre Surfsky adicional para sites técnicos;
    - respeita orçamento total entre fontes;
    - para cedo quando a ficha já ficou suficientemente completa.

    Uma chamada explícita com enrich=true continua podendo usar o modo completo.
    """

    def __init__(self, providers=None, auto_mode=False):
        self.auto_mode = bool(auto_mode)
        self.providers = providers or [
            ManufacturerProvider(),
            CPUWorldProvider(),
            CPUMonkeyProvider(),
            WikiChipProvider(),
            TechPowerUpProvider(),
            PCKomboProvider(),
            GeizhalsProvider(),
        ]

        if self.auto_mode:
            try:
                self.total_timeout = max(3.0, float(os.getenv("ENRICHMENT_AUTO_TOTAL_TIMEOUT_SECONDS", "18")))
            except ValueError:
                self.total_timeout = 18.0
            try:
                self.max_sources = max(1, int(os.getenv("ENRICHMENT_AUTO_MAX_SOURCES", "3")))
            except ValueError:
                self.max_sources = 3
            try:
                self.target_coverage = float(os.getenv("ENRICHMENT_AUTO_TARGET_COVERAGE", "0.70"))
            except ValueError:
                self.target_coverage = 0.70
            self.target_coverage = min(1.0, max(0.0, self.target_coverage))
            try:
                per_source_timeout = max(2, int(os.getenv("ENRICHMENT_AUTO_SOURCE_TIMEOUT", "5")))
            except ValueError:
                per_source_timeout = 5

            # No automático, a captura comercial já teve acesso ao Surfsky quando
            # necessário. Não abrir várias novas sessões cloud para cada fonte técnica.
            for provider in self.providers:
                provider.allow_browser_fallback = False
                if hasattr(provider, "timeout"):
                    provider.timeout = min(int(provider.timeout), per_source_timeout)
                resolver = getattr(provider, "resolver", None)
                if resolver is not None:
                    resolver.allow_browser_fallback = False
                    if hasattr(resolver, "timeout"):
                        resolver.timeout = min(int(resolver.timeout), per_source_timeout)
        else:
            self.total_timeout = None
            self.max_sources = None
            self.target_coverage = 1.0

    def enrich(self, result):
        output = deepcopy(result)
        identity = build_identity(output)
        category = output.get("categoriaDetectada")
        schema = SCHEMAS.get(category) if category else None
        spec_field = schema[1] if schema else None
        started = time.monotonic()

        info = {
            "executado": False,
            "modo": "AUTOMATICO_RAPIDO" if self.auto_mode else "COMPLETO",
            "identidade": identity,
            "fontesConsultadas": [],
            "camposPreenchidos": [],
            "origemPorCampo": {},
            "conflitos": [],
            "motivoIgnorado": None,
            "interrompidoPorTimeout": False,
            "interrompidoPorCobertura": False,
            "camposAusentesAntes": technical_missing_fields(output),
            "camposObrigatoriosAusentesAntes": required_missing_fields(output),
            "coberturaTecnicaAntes": round(technical_coverage(output), 4),
            "camposAusentesDepois": [],
            "camposObrigatoriosAusentesDepois": [],
            "coberturaTecnicaDepois": None,
        }

        if not identity_is_strong(identity):
            info["motivoIgnorado"] = "IDENTIDADE_INSUFICIENTE"
            output["enriquecimentoTecnico"] = info
            return output
        if not category or not spec_field:
            info["motivoIgnorado"] = "CATEGORIA_SEM_SCHEMA_TECNICO"
            output["enriquecimentoTecnico"] = info
            return output

        specs = dict(output.get("especificacoesEncontradas") or {})
        info["executado"] = True

        relevant = [
            p for p in self.providers
            if not hasattr(p, "supports") or p.supports(category, identity)
        ]
        if self.max_sources is not None:
            relevant = relevant[: self.max_sources]

        for provider in relevant:
            if self.total_timeout is not None and (time.monotonic() - started) >= self.total_timeout:
                info["interrompidoPorTimeout"] = True
                break

            try:
                source = provider.collect(identity, category)
            except Exception as exc:
                source = {
                    "ok": False,
                    "fonte": getattr(provider, "name", provider.__class__.__name__),
                    "erro": f"ERRO_PROVEDOR: {type(exc).__name__}: {exc}",
                }

            source_summary = {
                "fonte": source.get("fonte") or getattr(provider, "name", provider.__class__.__name__),
                "ok": bool(source.get("ok")),
                "url": source.get("url"),
                "erro": source.get("erro"),
                "modoColeta": source.get("modoColeta"),
            }
            info["fontesConsultadas"].append(source_summary)
            if source.get("ok"):
                external_specs = extract_specs(
                    category,
                    source.get("attributes") or [],
                    context_text=source.get("context_text") or "",
                )
                for field, external_value in external_specs.items():
                    if _missing(external_value):
                        continue
                    current = specs.get(field)
                    if _missing(current):
                        specs[field] = external_value
                        info["camposPreenchidos"].append(field)
                        info["origemPorCampo"][field] = {
                            "fonte": source_summary["fonte"],
                            "url": source_summary["url"],
                        }
                    elif _normalized_for_compare(current) != _normalized_for_compare(external_value):
                        info["conflitos"].append({
                            "campo": field,
                            "valorPrincipal": current,
                            "valorExterno": external_value,
                            "fonte": source_summary["fonte"],
                            "url": source_summary["url"],
                        })

            # Atualiza uma visão temporária para decidir se já podemos parar.
            temp = dict(output)
            temp["especificacoesEncontradas"] = specs
            if self.auto_mode and not required_missing_fields(temp) and technical_coverage(temp) >= self.target_coverage:
                info["interrompidoPorCobertura"] = True
                break

        info["camposPreenchidos"] = list(dict.fromkeys(info["camposPreenchidos"]))
        output["especificacoesEncontradas"] = specs
        payload = dict(output.get("payloadParcialBackend") or {})
        payload[spec_field] = specs
        output["payloadParcialBackend"] = payload
        output["camposObrigatoriosAusentes"] = [
            field for field in REQUIRED.get(category, []) if _missing(specs.get(field))
        ]
        info["camposAusentesDepois"] = technical_missing_fields(output)
        info["camposObrigatoriosAusentesDepois"] = required_missing_fields(output)
        info["coberturaTecnicaDepois"] = round(technical_coverage(output), 4)
        info["duracaoMs"] = int((time.monotonic() - started) * 1000)
        output["enriquecimentoTecnico"] = info
        return output


def apply_enrichment(result, providers=None, auto_mode=False):
    return TechnicalEnricher(providers=providers, auto_mode=auto_mode).enrich(result)
