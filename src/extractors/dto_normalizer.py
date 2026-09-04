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
    if token in {
        "true", "sim", "yes", "y", "1", "suportado", "supported", "incluido", "included",
        "habilitado", "enabled", "ativo", "active", "presente", "present", "possui", "has",
        "compativel", "compatible", "disponivel", "available",
    }:
        return True
    if token in {
        "false", "nao", "no", "n", "0", "nao_suportado", "unsupported", "sem", "none",
        "not_included", "desabilitado", "disabled", "inativo", "inactive", "ausente", "absent",
        "nao_possui", "does_not_have", "incompativel", "incompatible", "indisponivel", "unavailable",
    }:
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



def _m2_key(value: Any):
    token = _token(value)
    raw = _clean_text(value) or ""
    if not token:
        return None
    # B+M / B-M / B M / B&M são o mesmo enum B_M no backend.
    if re.search(r"\bB\s*(?:\+|&|/|-|_)\s*M\b", raw, re.I) or token in {"b_m", "bm", "b_and_m", "b_plus_m"}:
        return "B_M"
    if token in {"m", "m_key", "key_m", "chave_m"} or re.search(r"\bM[- ]?Key\b", raw, re.I):
        return "M"
    if token in {"b", "b_key", "key_b", "chave_b"} or re.search(r"\bB[- ]?Key\b", raw, re.I):
        return "B"
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



def _to_mhz(value: Any):
    if value is None or isinstance(value, bool):
        return None
    text = _clean_text(value) or ""
    # DDR5-6000 / DDR 4 3200 / PC5-48000 -> usa o clock explícito da memória,
    # nunca o número da geração DDR.
    m = re.search(r"\bDDR\s*[345]\s*[-_/ ]\s*(\d{3,5})\b", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"([-+]?\d[\d.,]*)\s*(GHz|MHz|MT/s|MTs|MHz effective)\b", text, re.I)
    if m:
        n = _to_number(m.group(1))
        if n is None:
            return None
        unit = m.group(2).casefold()
        return int(round(n * 1000)) if "ghz" in unit else int(round(n))
    n = _to_number(value)
    if n is None:
        return None
    # Em campos de frequência, valores abaixo de 20 quase sempre vieram em GHz.
    return int(round(n * 1000 if abs(n) < 20 else n))


def _to_gb(value: Any):
    if value is None or isinstance(value, bool):
        return None
    text = _clean_text(value) or ""
    m = re.search(r"([-+]?\d[\d.,]*)\s*(TB|GB|MB)\b", text, re.I)
    if m:
        n = _to_number(m.group(1))
        if n is None:
            return None
        unit = m.group(2).upper()
        if unit == "TB":
            n *= 1024
        elif unit == "MB":
            n /= 1024
        return int(round(n)) if float(n).is_integer() else round(float(n), 3)
    return _to_number(value)


def _to_mb(value: Any):
    if value is None or isinstance(value, bool):
        return None
    text = _clean_text(value) or ""
    m = re.search(r"([-+]?\d[\d.,]*)\s*(GB|MB|KB)\b", text, re.I)
    if m:
        n = _to_number(m.group(1))
        if n is None:
            return None
        unit = m.group(2).upper()
        if unit == "GB":
            n *= 1024
        elif unit == "KB":
            n /= 1024
        return round(float(n), 3)
    return _to_float(value)


def _to_mm(value: Any):
    if value is None or isinstance(value, bool):
        return None
    text = _clean_text(value) or ""
    m = re.search(r"([-+]?\d[\d.,]*)\s*(mm|cm)\b", text, re.I)
    if m:
        n = _to_number(m.group(1))
        if n is None:
            return None
        return float(n) * 10 if m.group(2).casefold() == "cm" else float(n)
    return _to_float(value)


def _to_watts(value: Any):
    if value is None or isinstance(value, bool):
        return None
    text = _clean_text(value) or ""
    m = re.search(r"([-+]?\d[\d.,]*)\s*(kW|W)\b", text, re.I)
    if m:
        n = _to_number(m.group(1))
        if n is None:
            return None
        return int(round(n * 1000)) if m.group(2).casefold() == "kw" else int(round(n))
    return _to_int(value)


def _frequency_list(value: Any):
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result = []
    for item in values:
        text = str(item or "")
        # Preserva a ordem da ficha (ex.: 7600/7200/6800/6400). Como frequências
        # de RAM relevantes têm 3-5 dígitos, DDR5 nunca vira o número 5.
        for raw in re.findall(r"\b(\d{3,5})\b", text):
            n = int(raw)
            if 400 <= n <= 20000:
                result.append(n)
    return _unique(result) or None


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

    # Meses em pt-BR/pt-PT são convertidos para inglês apenas para parsing.
    month_map = {
        "janeiro": "January", "jan": "Jan", "fevereiro": "February", "fev": "Feb",
        "marco": "March", "março": "March", "mar": "Mar", "abril": "April", "abr": "Apr",
        "maio": "May", "mai": "May", "junho": "June", "jun": "Jun", "julho": "July", "jul": "Jul",
        "agosto": "August", "ago": "Aug", "setembro": "September", "set": "Sep",
        "outubro": "October", "out": "Oct", "novembro": "November", "nov": "Nov",
        "dezembro": "December", "dez": "Dec",
    }
    parse_text = text
    tokenized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    for pt, en in month_map.items():
        pt_ascii = unicodedata.normalize("NFKD", pt).encode("ascii", "ignore").decode("ascii")
        if re.search(rf"\b{re.escape(pt_ascii)}\b", tokenized, re.I):
            parse_text = re.sub(rf"\b{re.escape(pt)}\b", en, parse_text, flags=re.I)
            tokenized = re.sub(rf"\b{re.escape(pt_ascii)}\b", en, tokenized, flags=re.I)
    if parse_text == text and tokenized != text:
        parse_text = tokenized

    # Formatos com nome do mês são inequívocos.
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(parse_text, fmt).replace(tzinfo=timezone.utc)
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



MHZ_FIELDS = {
    "PROCESSADOR": {"frequenciaBaseMhz", "frequenciaTurboMhz", "frequenciaMemoriaMaximaMhz"},
    "PLACA_MAE": set(),
    "MEMORIA_RAM": {"frequenciaMhz", "frequenciaJedecMhz"},
    "PLACA_VIDEO": {"clockBaseMhz", "clockBoostMhz"},
}

GB_FIELDS = {
    "PROCESSADOR": {"capacidadeMemoriaMaximaGb"},
    "PLACA_MAE": {"capacidadeMaximaMemoriaGb", "capacidadeMaximaPorSlotGb"},
    "MEMORIA_RAM": {"capacidadePorModuloGb"},
    "PLACA_VIDEO": {"memoriaVideoGb"},
    "ARMAZENAMENTO": {"capacidadeGb"},
}

MB_FIELDS = {"PROCESSADOR": {"cacheL2Mb", "cacheL3Mb"}}

MM_FIELDS = {
    "MEMORIA_RAM": {"alturaMm"},
    "PLACA_VIDEO": {"comprimentoMm", "alturaMm", "espessuraMm"},
    "ARMAZENAMENTO": {"alturaMm", "larguraMm", "profundidadeMm", "espessuraMm"},
    "FONTE": {"comprimentoMm", "larguraMm", "alturaMm"},
    "GABINETE": {"alturaMm", "larguraMm", "profundidadeMm", "comprimentoMaximoFonteMm", "comprimentoMaximoGpuMm", "alturaMaximaGpuMm", "alturaMaximaCoolerCpuMm", "espacoGerenciamentoCabosMm"},
    "COOLER": {"alturaMm", "larguraMm", "profundidadeMm", "alturaLivreRamMm", "tamanhoRadiadorMm", "espessuraRadiadorMm", "tamanhoVentoinhaMm", "espessuraVentoinhaMm", "comprimentoMangueirasMm"},
    "VENTOINHA": {"tamanhoMm", "espessuraMm"},
}

WATT_FIELDS = {
    "PROCESSADOR": {"tdpWatts"},
    "MEMORIA_RAM": {"consumoWatts"},
    "PLACA_VIDEO": {"consumoWatts", "potenciaFonteRecomendadaWatts"},
    "ARMAZENAMENTO": {"consumoWatts"},
    "FONTE": {"potenciaWatts"},
    "COOLER": {"capacidadeTermicaWatts", "consumoBombaWatts", "consumoWatts"},
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

    specialized = set()
    for field in MHZ_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _to_mhz(normalized[field])
            specialized.add(field)
    for field in GB_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _to_gb(normalized[field])
            specialized.add(field)
    for field in MB_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _to_mb(normalized[field])
            specialized.add(field)
    for field in MM_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _to_mm(normalized[field])
            specialized.add(field)
    for field in WATT_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _to_watts(normalized[field])
            specialized.add(field)

    for field in INT_FIELDS.get(category, set()):
        if field not in specialized and field in normalized and normalized[field] is not None:
            normalized[field] = _to_int(normalized[field])
    for field in FLOAT_FIELDS.get(category, set()):
        if field not in specialized and field in normalized and normalized[field] is not None:
            normalized[field] = _to_float(normalized[field])
    for field in INT_LIST_FIELDS.get(category, set()):
        if field in normalized and normalized[field] is not None:
            normalized[field] = _frequency_list(normalized[field]) if "frequenciasMemoria" in field else _int_list(normalized[field])

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
        if "chaveM2" in normalized:
            normalized["chaveM2"] = _m2_key(normalized.get("chaveM2"))

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
