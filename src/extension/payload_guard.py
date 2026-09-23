from __future__ import annotations

from typing import Any

from ..extractors.dto_normalizer import registration_payload_issues


_FONTE_FORMATOS = {"ATX", "SFX", "SFX_L", "TFX", "FLEX_ATX"}
_FONTE_MODULARIDADES = {"NAO_MODULAR", "SEMI_MODULAR", "MODULAR"}
_FONTE_CONECTORES = {
    "conectoresAtx24Pinos",
    "conectoresEpsCpu",
    "conectoresPcie6Pinos",
    "conectoresPcie8Pinos",
    "conectores12vhpwr",
    "conectores12v2x6",
    "conectoresSata",
    "conectoresMolex",
}
_FONTE_FLOAT_1M = {
    "comprimentoMm",
    "larguraMm",
    "alturaMm",
    "correnteLinha12vAmperes",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def sanitize_extension_hardware_payload(
    category: str | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Remove somente campos opcionais que o DTO do CriaByte certamente rejeita.

    Campos obrigatórios não são inventados nem corrigidos silenciosamente; eles
    permanecem para que ``extension_registration_issues`` mande o produto para
    revisão em vez de cadastrar ficha técnica errada.
    """
    category = str(category or "").upper()
    output = dict(payload or {})

    # Campos raiz opcionais: melhor omitir evidência fora do contrato do que
    # transformar um cadastro tecnicamente válido em HTTP 400.
    root_limits = {
        "descricao": 5000,
        "mpn": 150,
        "gtin": 32,
        "imagemUrl": 500,
        "imagemHoverUrl": 500,
    }
    for field, limit in root_limits.items():
        value = output.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            output.pop(field, None)

    if category != "FONTE":
        return output

    raw_specs = output.get("especificacaoFonte")
    if not isinstance(raw_specs, dict):
        return output

    specs = dict(raw_specs)

    modularidade = specs.get("modularidade")
    if modularidade is not None and modularidade not in _FONTE_MODULARIDADES:
        specs.pop("modularidade", None)

    for field in _FONTE_FLOAT_1M:
        value = specs.get(field)
        if value is not None and (not _is_number(value) or not 0 <= value <= 1_000_000):
            specs.pop(field, None)

    eficiencia = specs.get("eficienciaPercentual")
    if eficiencia is not None and (
        not _is_number(eficiencia) or not 0 <= eficiencia <= 100
    ):
        specs.pop("eficienciaPercentual", None)

    for field in _FONTE_CONECTORES:
        value = specs.get(field)
        if value is not None and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 0 <= value <= 128
        ):
            specs.pop(field, None)

    string_limits = {
        "certificacao": 100,
        "padraoAtx": 50,
        "tensaoEntrada": 100,
    }
    for field, limit in string_limits.items():
        value = specs.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            specs.pop(field, None)

    protecoes = specs.get("protecoes")
    if protecoes is not None:
        if not isinstance(protecoes, list):
            specs.pop("protecoes", None)
        else:
            clean = []
            seen = set()
            for item in protecoes:
                if not isinstance(item, str) or not item.strip() or len(item.strip()) > 80:
                    continue
                value = item.strip()
                key = value.casefold()
                if key in seen:
                    continue
                seen.add(key)
                clean.append(value)
                if len(clean) >= 32:
                    break
            if clean:
                specs["protecoes"] = clean
            else:
                specs.pop("protecoes", None)

    output["especificacaoFonte"] = specs
    return output


def extension_registration_issues(
    category: str | None,
    payload: dict[str, Any] | None,
) -> list[str]:
    category = str(category or (payload or {}).get("categoria") or "").upper()
    data = payload or {}
    issues = list(registration_payload_issues(category, data))

    root_required = {
        "nome": (2, 200),
        "marca": (1, 100),
        "modelo": (1, 150),
    }
    for field, (minimum, maximum) in root_required.items():
        value = data.get(field)
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
            issues.append(f"{field} ausente ou fora do formato aceito")

    if category != "FONTE":
        return list(dict.fromkeys(issues))

    specs = data.get("especificacaoFonte")
    if not isinstance(specs, dict):
        issues.append("especificacaoFonte ausente")
        return list(dict.fromkeys(issues))

    formato = specs.get("formato")
    if formato not in _FONTE_FORMATOS:
        issues.append("especificacaoFonte.formato não confirmado")

    potencia = specs.get("potenciaWatts")
    if (
        not isinstance(potencia, int)
        or isinstance(potencia, bool)
        or not 1 <= potencia <= 100_000
    ):
        issues.append("especificacaoFonte.potenciaWatts não confirmada")

    return list(dict.fromkeys(issues))
