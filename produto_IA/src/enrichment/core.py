from copy import deepcopy
import os
import time

from .identity import build_identity, identity_is_strong
from .providers import (
    ManufacturerProvider, TechPowerUpProvider, PCKomboProvider, GeizhalsProvider,
    CPUWorldProvider, WikiChipProvider, CPUMonkeyProvider, IcecatProvider,
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
    """Regra v14.15: QUALQUER lacuna técnica esperada dispara enriquecimento.

    A regra funcional do CriaByte é simples: se o marketplace não trouxe um campo
    técnico esperado e a identidade do produto é forte, a Produto IA deve tentar
    completar esse campo em fontes técnicas confiáveis.

    A proteção contra fila travada não é feita pulando o enriquecimento; ela é feita
    dentro do TechnicalEnricher, com orçamento de tempo, poucas fontes por rodada,
    timeouts curtos e parada assim que não houver mais campos ausentes.
    """
    if not identity_is_strong(build_identity(result or {})):
        return False
    return bool(technical_missing_fields(result))


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

    def __init__(self, providers=None, auto_mode=False, total_timeout_override=None, max_sources_override=None, source_timeout_override=None):
        self.auto_mode = bool(auto_mode)
        self.providers = providers or [
            IcecatProvider(),
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
                self.total_timeout = max(3.0, float(os.getenv("ENRICHMENT_AUTO_TOTAL_TIMEOUT_SECONDS", "20")))
            except ValueError:
                self.total_timeout = 20.0
            try:
                self.max_sources = max(1, int(os.getenv("ENRICHMENT_AUTO_MAX_SOURCES", "4")))
            except ValueError:
                self.max_sources = 4
            try:
                self.target_coverage = float(os.getenv("ENRICHMENT_AUTO_TARGET_COVERAGE", "1.0"))
            except ValueError:
                self.target_coverage = 1.0
            self.target_coverage = min(1.0, max(0.0, self.target_coverage))
            try:
                per_source_timeout = max(2, int(os.getenv("ENRICHMENT_AUTO_SOURCE_TIMEOUT", "4")))
            except ValueError:
                per_source_timeout = 4
            if total_timeout_override is not None:
                self.total_timeout = max(1.0, float(total_timeout_override))
            if max_sources_override is not None:
                self.max_sources = max(1, int(max_sources_override))
            if source_timeout_override is not None:
                per_source_timeout = max(1, int(source_timeout_override))

            # v14.15: não desliga o fallback cloud por completo, porque isso fazia
            # a regra "faltou no marketplace -> buscar nas fontes técnicas" falhar
            # justamente quando fabricante/buscador bloqueavam a Railway.
            #
            # Para controlar custo/latência:
            # - fabricante oficial pode usar Surfsky como fallback;
            # - provedores técnicos especializados ficam em HTTP no automático;
            # - o resolver do fabricante também pode usar Surfsky para descobrir a
            #   página oficial;
            # - demais resolvers não abrem sessões cloud extras.
            for provider in self.providers:
                is_manufacturer = isinstance(provider, ManufacturerProvider)
                provider.allow_browser_fallback = bool(is_manufacturer)
                if hasattr(provider, "timeout"):
                    provider.timeout = min(int(provider.timeout), per_source_timeout)
                rate_limiter = getattr(provider, "rate_limiter", None)
                if rate_limiter is not None:
                    rate_limiter.min_delay = min(rate_limiter.min_delay, 0.35)
                    rate_limiter.jitter = min(rate_limiter.jitter, 0.15)
                resolver = getattr(provider, "resolver", None)
                if resolver is not None:
                    resolver.allow_browser_fallback = bool(is_manufacturer)
                    if hasattr(resolver, "timeout"):
                        resolver.timeout = min(int(resolver.timeout), per_source_timeout)
                    resolver_limiter = getattr(resolver, "rate_limiter", None)
                    if resolver_limiter is not None:
                        resolver_limiter.min_delay = min(resolver_limiter.min_delay, 0.35)
                        resolver_limiter.jitter = min(resolver_limiter.jitter, 0.15)
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
            missing_now = technical_missing_fields(temp)
            if self.auto_mode and not missing_now:
                info["interrompidoPorCobertura"] = True
                break
            # Permite reduzir o alvo por variável em ambientes que precisem de um
            # orçamento ainda mais agressivo, mas o padrão v14.15 é 100%.
            if self.auto_mode and self.target_coverage < 1.0 \
                    and not required_missing_fields(temp) \
                    and technical_coverage(temp) >= self.target_coverage:
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
