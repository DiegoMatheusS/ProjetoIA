from copy import deepcopy

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
    """Retorna campos técnicos esperados ainda ausentes.

    A v14.12 usa isso para disparar enriquecimento automaticamente quando a
    página comercial (Magalu/ML) não possui a ficha completa. Não se limita aos
    campos mínimos obrigatórios do cadastro.
    """
    category = (result or {}).get("categoriaDetectada")
    schema = SCHEMAS.get(category) if category else None
    if not schema or not schema[1]:
        return []
    expected = schema[2] or []
    specs = (result or {}).get("especificacoesEncontradas") or {}
    return [field for field in expected if _missing(specs.get(field))]


def should_auto_enrich(result):
    """Enriquecimento obrigatório quando existe identidade forte e lacuna técnica."""
    if not technical_missing_fields(result):
        return False
    return identity_is_strong(build_identity(result or {}))


class TechnicalEnricher:
    """Complementa apenas campos técnicos ausentes.

    Regra de segurança:
    - exige identidade forte;
    - fabricante oficial vem primeiro;
    - fonte secundária nunca sobrescreve silenciosamente um valor existente;
    - conflitos ficam registrados para revisão.
    """

    def __init__(self, providers=None):
        self.providers = providers or [
            ManufacturerProvider(),
            CPUWorldProvider(),
            CPUMonkeyProvider(),
            WikiChipProvider(),
            TechPowerUpProvider(),
            PCKomboProvider(),
            GeizhalsProvider(),
        ]

    def enrich(self, result):
        output = deepcopy(result)
        identity = build_identity(output)
        category = output.get("categoriaDetectada")
        schema = SCHEMAS.get(category) if category else None
        spec_field = schema[1] if schema else None

        info = {
            "executado": False,
            "identidade": identity,
            "fontesConsultadas": [],
            "camposPreenchidos": [],
            "origemPorCampo": {},
            "conflitos": [],
            "motivoIgnorado": None,
            "camposAusentesAntes": technical_missing_fields(output),
            "camposAusentesDepois": [],
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

        for provider in self.providers:
            source = provider.collect(identity, category)
            source_summary = {
                "fonte": source.get("fonte") or getattr(provider, "name", provider.__class__.__name__),
                "ok": bool(source.get("ok")),
                "url": source.get("url"),
                "erro": source.get("erro"),
            }
            info["fontesConsultadas"].append(source_summary)
            if not source.get("ok"):
                continue

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

        # Remove duplicatas mantendo a ordem de descoberta.
        info["camposPreenchidos"] = list(dict.fromkeys(info["camposPreenchidos"]))
        output["especificacoesEncontradas"] = specs
        payload = dict(output.get("payloadParcialBackend") or {})
        payload[spec_field] = specs
        output["payloadParcialBackend"] = payload
        output["camposObrigatoriosAusentes"] = [
            field for field in REQUIRED.get(category, []) if _missing(specs.get(field))
        ]
        info["camposAusentesDepois"] = technical_missing_fields(output)
        output["enriquecimentoTecnico"] = info
        return output


def apply_enrichment(result, providers=None):
    return TechnicalEnricher(providers=providers).enrich(result)
