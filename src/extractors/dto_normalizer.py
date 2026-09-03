from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Any


def _clean_text(value: Any):
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _token(value: Any) -> str:
    text = _clean_text(value) or ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def _unique(values):
    out = []
    seen = set()
    for value in values:
        if value in (None, "", []):
            continue
        key = str(value).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _to_number(value: Any):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = _clean_text(value)
    if not text:
        return None
    match = re.search(r"[-+]?\d[\d.,]*", text)
    if not match:
        return None
    raw = match.group(0)
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
    elif "." in raw and re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _to_int(value: Any):
    number = _to_number(value)
    if number is None:
        return None
    if float(number).is_integer():
        return int(number)
    return None


def _to_float(value: Any):
    number = _to_number(value)
    return float(number) if number is not None else None


def _to_bool(value: Any):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    token = _token(value)
    if token in {"true", "sim", "yes", "y", "1", "suportado", "supported", "incluido", "included"}:
        return True
    if token in {"false", "nao", "no", "n", "0", "nao_suportado", "unsupported", "sem", "none", "not_included"}:
        return False
    return None


def _memory_types(value: Any):
    values = value if isinstance(value, (list, tuple, set)) else [value]
    found = []
    for item in values:
        for generation in re.findall(r"\bDDR\s*[-_ ]?([345])\b", str(item or ""), re.I):
            found.append(f"DDR{generation}")
    return _unique(found) or None


def _single_memory_type(value: Any):
    values = _memory_types(value) or []
    return values[0] if len(values) == 1 else None


def _ram_form(value: Any):
    token = _token(value)
    if not token:
        return None
    if "so_dimm" in token or "sodimm" in token:
        return "SO_DIMM"
    if "udimm" in token or "dimm" in token:
        return "DIMM"
    return None


def _memory_forms(value: Any):
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;/|]+", str(value or ""))
    result = []
    for item in values:
        text = str(item or "")
        if re.search(r"\bSO[-_ ]?DIMM\b", text, re.I):
            result.append("SO_DIMM")
        elif re.search(r"\b(?:U?DIMM)\b", text, re.I):
            result.append("DIMM")
    return _unique(result) or None


def _motherboard_form(value: Any):
    token = _token(value)
    if not token:
        return None
    if "mini_itx" in token or token == "itx":
        return "MINI_ITX"
    if "micro_atx" in token or "microatx" in token or token in {"matx", "m_atx"}:
        return "MICRO_ATX"
    if "e_atx" in token or "eatx" in token or "extended_atx" in token:
        return "E_ATX"
    if token == "atx" or token.startswith("atx_"):
        return "ATX"
    return None


def _motherboard_forms(value: Any):
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;/|]+", str(value or ""))
    return _unique(_motherboard_form(item) for item in values) or None


def _psu_format(value: Any):
    token = _token(value)
    if not token:
        return None
    if "sfx_l" in token or "sfxl" in token:
        return "SFX_L"
    if token == "sfx" or token.startswith("sfx_"):
        return "SFX"
    if "flex_atx" in token:
        return "FLEX_ATX"
    if token == "tfx" or token.startswith("tfx_"):
        return "TFX"
    if token == "atx" or token.startswith("atx_") or "_atx_" in token:
        return "ATX"
    return None


def _psu_formats(value: Any):
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;/|]+", str(value or ""))
    return _unique(_psu_format(item) for item in values) or None


def _case_size(value: Any):
    token = _token(value)
    if not token:
        return None
    if "full_tower" in token:
        return "FULL_TOWER"
    if "mid_tower" in token or "midtower" in token:
        return "MID_TOWER"
    if "mini_tower" in token or "minitower" in token:
        return "MINI_TOWER"
    if token in {"sff", "small_form_factor"}:
        return "SFF"
    if "open_frame" in token:
        return "OPEN_FRAME"
    return None


def _storage_type(value: Any):
    token = _token(value)
    if not token:
        return None
    if "ssd" in token or "solid_state" in token or "nvme" in token:
        return "SSD"
    if token == "hdd" or "hard_disk" in token or "hard_drive" in token or "disco_rigido" in token:
        return "HDD"
    return None


def _storage_format(value: Any):
    token = _token(value)
    raw = str(value or "")
    if not token:
        return None
    if "m_2" in token or token == "m2" or re.search(r"\b22(?:30|42|60|80|110)\b", raw):
        return "M2"
    if "2_5" in token:
        return "POLEGADAS_2_5"
    if "3_5" in token:
        return "POLEGADAS_3_5"
    if "pcie" in token and ("placa" in token or "add_in" in token or "aic" in token):
        return "PLACA_PCIE"
    return None


def _storage_interface(value: Any):
    text = _clean_text(value) or ""
    if re.search(r"\bNVMe\b", text, re.I) or (re.search(r"\bPCIe?\b|PCI\s*Express", text, re.I) and not re.search(r"\bSATA\b", text, re.I)):
        return "NVME_PCIE"
    if re.search(r"\bSAS\b", text, re.I):
        return "SAS"
    if re.search(r"\bSATA\b", text, re.I):
        return "SATA"
    token = _token(value)
    if token in {"nvme_pcie", "sata", "sas"}:
        return token.upper()
    return None


def _modularity(value: Any):
    token = _token(value)
    text = _clean_text(value) or ""
    if not token:
        return None
    if token in {"nao_modular", "non_modular", "nao", "no", "false"} or re.search(r"\b(?:non|nao)\s*[- ]?modular\b", text, re.I):
        return "NAO_MODULAR"
    if "semi_modular" in token or "semimodular" in token:
        return "SEMI_MODULAR"
    if token in {"modular", "full_modular", "totalmente_modular", "completamente_modular", "sim", "yes", "true"} or re.search(r"\b(?:full|totalmente|completamente)\s+modular\b", text, re.I):
        return "MODULAR"
    return None


def _cooler_type(value: Any):
    token = _token(value)
    if not token:
        return None
    if token in {"air_cooler", "air", "cooler_a_ar"} or "air_cooler" in token or "tower_cooler" in token:
        return "AIR_COOLER"
    if token in {"water_cooler", "water", "aio", "liquid_cooler"} or "water_cooler" in token or "liquid_cooler" in token:
        return "WATER_COOLER"
    return None


def _fan_connector(value: Any):
    token = _token(value)
    if not token:
        return None
    if "4_pinos" in token or "4_pin" in token or "pwm" in token:
        return "PWM_4_PINOS"
    if "3_pinos" in token or "3_pin" in token:
        return "DC_3_PINOS"
    if "molex" in token:
        return "MOLEX"
    if "propriet" in token:
        return "PROPRIETARIO"
    return None


def _socket_list(value: Any):
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;/|]+", str(value or ""))
    result = []
    for item in values:
        raw = _clean_text(item)
        if not raw:
            continue
        for match in re.findall(r"(?:FC)?LGA\s*\d{3,4}|AM[2345]|TR4|sTRX4|sTR5|sWRX8", raw, re.I):
            m = re.search(r"(?:FC)?LGA\s*(\d{3,4})", match, re.I)
            if m:
                result.append(f"LGA{m.group(1)}")
            else:
                result.append(re.sub(r"\s+", "", match).upper())
    return _unique(result) or None


def _string_list(value: Any):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = re.split(r"[,;|\n]+", str(value))
    return _unique(_clean_text(item) for item in values) or None


def _int_list(value: Any):
    values = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;/|\s]+", str(value or ""))
    result = []
    for item in values:
        number = _to_int(item)
        if number is not None:
            result.append(number)
    return _unique(result) or None


def _pcie_version(value: Any):
    if value is None:
        return None
    match = re.search(r"\b([1-9](?:[.,]\d+)?)\b", str(value))
    if not match:
        return None
    number = match.group(1).replace(",", ".")
    if "." not in number:
        number += ".0"
    return number


def _iso_date(value: Any):
    """Normaliza somente datas completas e confiáveis para ISO 8601 UTC.

    Ano isolado ou mês/ano são descartados em vez de inventar dia/mês.
    Datas numéricas ambíguas (ex.: 07/08/2020) também são descartadas.
    """
    text = _clean_text(value)
    if not text:
        return None
    if re.fullmatch(r"\d{4}", text) or re.fullmatch(r"\d{1,2}[/-]\d{4}", text):
        return None
    text = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", text, flags=re.I)

    # ISO / ano-mês-dia é inequívoco.
    iso = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})(?:[T\s].*)?$", text)
    if iso:
        try:
            dt = datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)), tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT00:00:00.000Z")
        except ValueError:
            return None

    # Formatos com nome do mês são inequívocos.
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT00:00:00.000Z")
        except ValueError:
            pass

    numeric = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if numeric:
        a, b, year = map(int, numeric.groups())
        if a <= 12 and b <= 12:
            return None
        day, month = (a, b) if a > 12 else (b, a)
        try:
            dt = datetime(year, month, day, tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT00:00:00.000Z")
        except ValueError:
            return None
    return None


BOOL_FIELDS = {
    "PROCESSADOR": {"possuiVideoIntegrado", "suportaEcc", "coolerIncluso", "multiplicadorDesbloqueado", "suporteOverclock"},
    "PLACA_MAE": {"suportaXmp", "suportaExpo", "suportaEcc", "suportaMemoriaRegistrada", "wifi", "bluetooth", "biosFlashback"},
    "MEMORIA_RAM": {"ecc", "registrada", "suportaXmp", "suportaExpo", "rgb"},
    "ARMAZENAMENTO": {"possuiDissipador"},
    "GABINETE": {"suportaGpuVertical"},
    "COOLER": {"rgb", "argb"},
    "VENTOINHA": {"pwm", "rgb", "argb", "fluxoReverso"},
}

INT_FIELDS = {
    "PROCESSADOR": {"litografiaNm", "nucleos", "threads", "frequenciaBaseMhz", "frequenciaTurboMhz", "tdpWatts", "frequenciaMemoriaMaximaMhz", "capacidadeMemoriaMaximaGb", "canaisMemoria", "lanesPcie"},
    "PLACA_MAE": {"slotsMemoria", "capacidadeMaximaMemoriaGb", "capacidadeMaximaPorSlotGb", "portasSata", "slotsM2"},
    "MEMORIA_RAM": {"capacidadePorModuloGb", "quantidadeModulos", "frequenciaMhz", "frequenciaJedecMhz", "latenciaCl"},
    "PLACA_VIDEO": {"memoriaVideoGb", "barramentoBits", "clockBaseMhz", "clockBoostMhz", "geracaoPcie", "larguraPcie", "consumoWatts", "potenciaFonteRecomendadaWatts", "conectoresPcie6Pinos", "conectoresPcie8Pinos", "conectores12vhpwr", "conectores12v2x6", "hdmi", "displayPort"},
    "ARMAZENAMENTO": {"capacidadeGb", "tamanhoM2Mm", "geracaoPcie", "pistasPcie", "leituraSequencialMbps", "escritaSequencialMbps"},
    "FONTE": {"potenciaWatts", "conectoresAtx24Pinos", "conectoresEpsCpu", "conectoresPcie6Pinos", "conectoresPcie8Pinos", "conectores12vhpwr", "conectores12v2x6", "conectoresSata", "conectoresMolex"},
    "GABINETE": {"comprimentoMaximoFonteMm", "comprimentoMaximoGpuMm", "alturaMaximaGpuMm", "baias25", "baias35", "slotsTraseiros"},
    "COOLER": {"capacidadeTermicaWatts", "tamanhoRadiadorMm", "quantidadeVentoinhas", "tamanhoVentoinhaMm", "vidaUtilHoras", "pesoGramas", "velocidadeMaxRpm"},
    "VENTOINHA": {"tamanhoMm", "rpmMinima", "rpmMaxima"},
}

FLOAT_FIELDS = {
    "PROCESSADOR": {"cacheL2Mb", "cacheL3Mb", "temperaturaMaximaC"},
    "MEMORIA_RAM": {"tensaoVolts", "alturaMm", "consumoWatts"},
    "PLACA_VIDEO": {"comprimentoMm", "alturaMm", "espessuraMm", "slotsOcupados"},
    "ARMAZENAMENTO": {"alturaMm", "larguraMm", "profundidadeMm", "espessuraMm", "consumoWatts"},
    "FONTE": {"comprimentoMm", "larguraMm", "alturaMm", "eficienciaPercentual", "correnteLinha12vAmperes"},
    "GABINETE": {"alturaMm", "larguraMm", "profundidadeMm", "slotsMaximosGpu", "alturaMaximaCoolerCpuMm", "espacoGerenciamentoCabosMm"},
    "COOLER": {"alturaMm", "larguraMm", "profundidadeMm", "alturaLivreRamMm", "espessuraRadiadorMm", "espessuraVentoinhaMm", "comprimentoMangueirasMm", "consumoBombaWatts", "consumoWatts", "ruidoDb", "fluxoArCfm"},
    "VENTOINHA": {"espessuraMm", "fluxoArCfm", "pressaoEstaticaMmH2o", "ruidoDb", "tensaoVolts", "correnteAmperes"},
}

INT_LIST_FIELDS = {
    "PLACA_MAE": {"frequenciasMemoriaJedecMhz", "frequenciasMemoriaOverclockMhz"},
}


def normalize_specs_for_backend(category: str | None, specs: dict | None) -> dict:
    """Última barreira antes do payload do CriaByte.

    Converte apenas formatos inequivocamente aceitos pelo contrato do backend.
    Valor ambíguo/inválido vira None para ser exibido como campo ausente, em vez
    de causar 400 no cadastro ou inventar informação técnica.
    """
    category = str(category or "").upper()
    normalized = dict(specs or {})

    for field in BOOL_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _to_bool(normalized[field])
    for field in INT_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _to_int(normalized[field])
    for field in FLOAT_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _to_float(normalized[field])
    for field in INT_LIST_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _int_list(normalized[field])

    if category == "PROCESSADOR":
        if "tiposMemoriaSuportados" in normalized:
            normalized["tiposMemoriaSuportados"] = _memory_types(normalized.get("tiposMemoriaSuportados"))
        if "versaoPcie" in normalized:
            normalized["versaoPcie"] = _pcie_version(normalized.get("versaoPcie"))
        if "dataLancamento" in normalized:
            normalized["dataLancamento"] = _iso_date(normalized.get("dataLancamento"))

    elif category == "PLACA_MAE":
        if "formato" in normalized:
            normalized["formato"] = _motherboard_form(normalized.get("formato"))
        if "tiposMemoriaSuportados" in normalized:
            normalized["tiposMemoriaSuportados"] = _memory_types(normalized.get("tiposMemoriaSuportados"))
        if "formatosMemoriaSuportados" in normalized:
            normalized["formatosMemoriaSuportados"] = _memory_forms(normalized.get("formatosMemoriaSuportados"))
        if "versaoPcie" in normalized:
            normalized["versaoPcie"] = _pcie_version(normalized.get("versaoPcie"))
        if "saidasVideo" in normalized:
            normalized["saidasVideo"] = _string_list(normalized.get("saidasVideo"))

    elif category == "MEMORIA_RAM":
        if "tipo" in normalized:
            normalized["tipo"] = _single_memory_type(normalized.get("tipo"))
        if "formato" in normalized:
            normalized["formato"] = _ram_form(normalized.get("formato"))

    elif category == "PLACA_VIDEO":
        if "saidasVideo" in normalized:
            normalized["saidasVideo"] = _string_list(normalized.get("saidasVideo"))

    elif category == "ARMAZENAMENTO":
        if "tipo" in normalized:
            normalized["tipo"] = _storage_type(normalized.get("tipo"))
        if "formato" in normalized:
            normalized["formato"] = _storage_format(normalized.get("formato"))
        if "interface" in normalized:
            normalized["interface"] = _storage_interface(normalized.get("interface"))

    elif category == "FONTE":
        if "formato" in normalized:
            normalized["formato"] = _psu_format(normalized.get("formato"))
        if "modularidade" in normalized:
            normalized["modularidade"] = _modularity(normalized.get("modularidade"))
        if "protecoes" in normalized:
            normalized["protecoes"] = _string_list(normalized.get("protecoes"))

    elif category == "GABINETE":
        if "tamanho" in normalized:
            normalized["tamanho"] = _case_size(normalized.get("tamanho"))
        if "formatosPlacaMaeSuportados" in normalized:
            normalized["formatosPlacaMaeSuportados"] = _motherboard_forms(normalized.get("formatosPlacaMaeSuportados"))
        if "formatosFonteSuportados" in normalized:
            normalized["formatosFonteSuportados"] = _psu_formats(normalized.get("formatosFonteSuportados"))

    elif category == "COOLER":
        if "tipo" in normalized:
            normalized["tipo"] = _cooler_type(normalized.get("tipo"))
        if "socketsSuportados" in normalized:
            normalized["socketsSuportados"] = _socket_list(normalized.get("socketsSuportados"))

    elif category == "VENTOINHA":
        if "conector" in normalized:
            normalized["conector"] = _fan_connector(normalized.get("conector"))

    return normalized


SPEC_FIELD_BY_HARDWARE_CATEGORY = {
    "PROCESSADOR": "especificacaoProcessador",
    "PLACA_MAE": "especificacaoPlacaMae",
    "MEMORIA_RAM": "especificacaoMemoriaRam",
    "PLACA_VIDEO": "especificacaoPlacaVideo",
    "ARMAZENAMENTO": "especificacaoArmazenamento",
    "FONTE": "especificacaoFonte",
    "GABINETE": "especificacaoGabinete",
    "COOLER": "especificacaoCooler",
    "VENTOINHA": "especificacaoVentoinha",
}


def normalize_hardware_payload_for_backend(category: str | None, payload: dict | None) -> dict:
    """Barreira final do payload de descoberta antes de sair da Produto IA.

    A descoberta passa por vários parsers/fontes. Mesmo que alguma etapa devolva
    um enum composto (ex.: ``DDR4/DDR5``), esta função normaliza novamente o
    bloco técnico *aninhado* que será reenviado pelo frontend ao Nest.

    Não inventa dados: valores incompatíveis viram ``None``. Em especial,
    ``tiposMemoriaSuportados`` de PROCESSADOR/PLACA_MAE nunca pode sair com
    itens fora de DDR3/DDR4/DDR5.
    """
    category = str(category or (payload or {}).get("categoria") or "").upper()
    output = dict(payload or {})
    spec_field = SPEC_FIELD_BY_HARDWARE_CATEGORY.get(category)
    if not spec_field:
        return output

    raw_specs = output.get(spec_field)
    specs = normalize_specs_for_backend(category, raw_specs if isinstance(raw_specs, dict) else {})
    # Payload de cadastro deve conter somente chaves conhecidas pelo DTO.
    # Import local evita acoplamento no carregamento do módulo.
    try:
        from .backend_schemas import SCHEMAS
        expected = (SCHEMAS.get(category) or (None, None, []))[2] or []
    except Exception:
        expected = []
    if expected:
        specs = {field: specs.get(field) for field in expected}

    # Defesa explícita para o erro real visto no DTO do Nest.
    if category in {"PROCESSADOR", "PLACA_MAE"}:
        memory = _memory_types(specs.get("tiposMemoriaSuportados"))
        specs["tiposMemoriaSuportados"] = [
            value for value in (memory or []) if value in {"DDR3", "DDR4", "DDR5"}
        ] or None

    output["categoria"] = category
    output[spec_field] = specs
    return output
