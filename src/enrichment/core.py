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




def complete_specs(category, specs):
    """Retorna todos os campos do schema técnico com None para os ausentes."""
    schema = SCHEMAS.get(category) if category else None
    expected = (schema[2] if schema else None) or []
    source = dict(specs or {})
    completed = {field: source.get(field) for field in expected}
    for key, value in source.items():
        if key not in completed:
            completed[key] = value
    return completed


PROVIDER_PRIORITY = {
    "PROCESSADOR": ["ICECAT", "CPU_MONKEY", "FABRICANTE_OFICIAL", "CPU_WORLD", "WIKICHIP", "PC_KOMBO", "GEIZHALS"],
    "PLACA_VIDEO": ["ICECAT", "TECHPOWERUP", "FABRICANTE_OFICIAL", "PC_KOMBO", "WIKICHIP", "GEIZHALS"],
    "PLACA_MAE": ["ICECAT", "FABRICANTE_OFICIAL", "PC_KOMBO", "GEIZHALS"],
    "MEMORIA_RAM": ["ICECAT", "FABRICANTE_OFICIAL", "PC_KOMBO", "GEIZHALS"],
    "ARMAZENAMENTO": ["ICECAT", "FABRICANTE_OFICIAL", "PC_KOMBO", "GEIZHALS"],
    "FONTE": ["ICECAT", "FABRICANTE_OFICIAL", "PC_KOMBO", "GEIZHALS"],
    "GABINETE": ["ICECAT", "FABRICANTE_OFICIAL", "PC_KOMBO", "GEIZHALS"],
    "COOLER": ["ICECAT", "FABRICANTE_OFICIAL", "PC_KOMBO", "GEIZHALS"],
    "VENTOINHA": ["ICECAT", "FABRICANTE_OFICIAL", "PC_KOMBO", "GEIZHALS"],
}


def _provider_rank(category, provider):
    order = PROVIDER_PRIORITY.get(category) or []
    name = getattr(provider, "name", provider.__class__.__name__)
    try:
        return order.index(name)
    except ValueError:
        return len(order) + 10




# v14.20: cobertura técnica ponderada por categoria. Campos que definem
# compatibilidade/identidade funcional pesam mais que metadados raros.
COVERAGE_WEIGHT_TIERS = {
    "PROCESSADOR": {
        "essenciais": ["socket", "nucleos", "threads", "frequenciaBaseMhz", "frequenciaTurboMhz", "tdpWatts", "cacheL3Mb", "tiposMemoriaSuportados", "versaoPcie"],
        "importantes": ["arquitetura", "litografiaNm", "cacheL2Mb", "frequenciaMemoriaMaximaMhz", "capacidadeMemoriaMaximaGb", "canaisMemoria", "possuiVideoIntegrado", "modeloVideoIntegrado"],
    },
    "MEMORIA_RAM": {
        "essenciais": ["tipo", "formato", "capacidadePorModuloGb", "quantidadeModulos", "frequenciaMhz"],
        "importantes": ["frequenciaJedecMhz", "latenciaCl", "tensaoVolts", "ecc", "registrada", "suportaXmp", "suportaExpo", "rgb"],
    },
    "PLACA_MAE": {
        "essenciais": ["socket", "chipset", "formato", "tiposMemoriaSuportados", "slotsMemoria", "capacidadeMaximaMemoriaGb", "versaoPcie", "slotsM2"],
        "importantes": ["frequenciasMemoriaJedecMhz", "frequenciasMemoriaOverclockMhz", "portasSata", "wifi", "bluetooth", "ethernet", "suportaXmp", "suportaExpo"],
    },
    "PLACA_VIDEO": {
        "essenciais": ["gpu", "memoriaVideoGb", "tipoMemoriaVideo", "barramentoBits", "geracaoPcie", "consumoWatts", "comprimentoMm", "slotsOcupados"],
        "importantes": ["clockBaseMhz", "clockBoostMhz", "potenciaFonteRecomendadaWatts", "conectoresPcie8Pinos", "conectores12vhpwr", "conectores12v2x6", "hdmi", "displayPort"],
    },
    "ARMAZENAMENTO": {
        "essenciais": ["tipo", "capacidadeGb", "interface", "formato"],
        "importantes": ["geracaoPcie", "pistasPcie", "leituraSequencialMbps", "escritaSequencialMbps", "tamanhoM2Mm", "possuiDissipador"],
    },
    "FONTE": {
        "essenciais": ["formato", "potenciaWatts", "certificacao", "modularidade", "padraoAtx"],
        "importantes": ["eficienciaPercentual", "comprimentoMm", "conectoresAtx24Pinos", "conectoresEpsCpu", "conectoresPcie8Pinos", "conectores12vhpwr", "conectores12v2x6", "protecoes"],
    },
    "GABINETE": {
        "essenciais": ["tamanho", "alturaMm", "larguraMm", "profundidadeMm", "formatosPlacaMaeSuportados", "comprimentoMaximoGpuMm", "alturaMaximaCoolerCpuMm"],
        "importantes": ["formatosFonteSuportados", "comprimentoMaximoFonteMm", "slotsTraseiros", "suportesFans", "suportesRadiador", "suportaGpuVertical"],
    },
    "COOLER": {
        "essenciais": ["tipo", "socketsSuportados", "alturaMm", "capacidadeTermicaWatts", "tamanhoVentoinhaMm", "velocidadeMaxRpm", "fluxoArCfm", "ruidoDb"],
        "importantes": ["tamanhoRadiadorMm", "quantidadeVentoinhas", "pesoGramas", "vidaUtilHoras", "rgb", "argb"],
    },
    "VENTOINHA": {
        "essenciais": ["tamanhoMm", "rpmMaxima", "fluxoArCfm", "pressaoEstaticaMmH2o", "ruidoDb", "conector", "pwm"],
        "importantes": ["espessuraMm", "rpmMinima", "tensaoVolts", "correnteAmperes", "rgb", "argb"],
    },
}

def _field_weight(category, field):
    tiers = COVERAGE_WEIGHT_TIERS.get(category) or {}
    if field in (tiers.get("essenciais") or []):
        return 3
    if field in (tiers.get("importantes") or []):
        return 2
    return 1

def essential_missing_fields(result):
    category = (result or {}).get("categoriaDetectada")
    specs = (result or {}).get("especificacoesEncontradas") or {}
    essentials = (COVERAGE_WEIGHT_TIERS.get(category) or {}).get("essenciais") or []
    return [field for field in essentials if _missing(specs.get(field))]

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
    total_weight = sum(_field_weight(category, field) for field in expected)
    present_weight = sum(
        _field_weight(category, field)
        for field in expected
        if not _missing(specs.get(field))
    )
    return present_weight / max(1, total_weight)


def technical_status(result, conflicts=None):
    """Status v14.20: cobertura ponderada + ausência de campos essenciais."""
    coverage = technical_coverage(result)
    essential_missing = essential_missing_fields(result)
    conflicts = conflicts if conflicts is not None else ((result or {}).get("conflitos") or [])
    if coverage < 0.55:
        return "FICHA_INCOMPLETA"
    if conflicts or essential_missing or coverage < 0.80:
        return "PRECISA_REVISAO"
    return "PRONTO"


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

    def __init__(
        self,
        providers=None,
        auto_mode=False,
        total_timeout_override=None,
        max_sources_override=None,
        source_timeout_override=None,
        target_coverage_override=None,
        excluded_sources=None,
    ):
        self.auto_mode = bool(auto_mode)
        self.excluded_sources = {
            str(value).strip().upper() for value in (excluded_sources or set()) if value
        }
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
            if target_coverage_override is not None:
                self.target_coverage = min(1.0, max(0.0, float(target_coverage_override)))
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
            "modo": "AUTOMATICO_CONTROLADO" if self.auto_mode else "COMPLETO",
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
            if (not hasattr(p, "supports") or p.supports(category, identity))
            and str(getattr(p, "name", "")).strip().upper() not in self.excluded_sources
        ]
        relevant.sort(key=lambda provider: _provider_rank(category, provider))
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
                    and not essential_missing_fields(temp) \
                    and technical_coverage(temp) >= self.target_coverage:
                info["interrompidoPorCobertura"] = True
                break

        info["camposPreenchidos"] = list(dict.fromkeys(info["camposPreenchidos"]))
        specs = complete_specs(category, specs)
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
