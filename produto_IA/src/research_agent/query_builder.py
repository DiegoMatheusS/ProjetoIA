from __future__ import annotations

import re
from collections.abc import Iterable


_FIELD_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "PROCESSADOR": {
        "arquitetura": ("architecture",),
        "litografiaNm": ("process node", "nm"),
        "nucleos": ("cores",),
        "threads": ("threads",),
        "frequenciaBaseMhz": ("base clock",),
        "frequenciaTurboMhz": ("boost clock",),
        "cacheL2Mb": ("L2 cache",),
        "cacheL3Mb": ("L3 cache",),
        "tdpWatts": ("TDP",),
        "tiposMemoriaSuportados": ("memory support", "DDR"),
        "frequenciaMemoriaMaximaMhz": ("maximum memory speed",),
        "capacidadeMemoriaMaximaGb": ("maximum memory",),
        "canaisMemoria": ("memory channels",),
        "versaoPcie": ("PCIe version",),
        "lanesPcie": ("PCIe lanes",),
        "possuiVideoIntegrado": ("integrated graphics",),
        "modeloVideoIntegrado": ("integrated graphics",),
    },
    "PLACA_VIDEO": {
        "gpu": ("GPU",),
        "arquitetura": ("architecture",),
        "memoriaVideoGb": ("VRAM",),
        "tipoMemoriaVideo": ("memory type",),
        "barramentoBits": ("memory bus",),
        "clockBaseMhz": ("base clock",),
        "clockBoostMhz": ("boost clock",),
        "geracaoPcie": ("PCIe",),
        "larguraPcie": ("PCIe lanes",),
        "consumoWatts": ("power consumption", "TDP"),
        "potenciaFonteRecomendadaWatts": ("recommended PSU",),
        "conectoresPcie6Pinos": ("power connector",),
        "conectoresPcie8Pinos": ("power connector",),
        "conectores12vhpwr": ("12VHPWR",),
        "conectores12v2x6": ("12V-2x6",),
        "comprimentoMm": ("dimensions length",),
        "alturaMm": ("dimensions height",),
        "espessuraMm": ("dimensions thickness",),
        "slotsOcupados": ("slot width",),
        "hdmi": ("HDMI outputs",),
        "displayPort": ("DisplayPort outputs",),
        "saidasVideo": ("display outputs",),
    },
    "PLACA_MAE": {
        "socket": ("socket",),
        "chipset": ("chipset",),
        "formato": ("form factor",),
        "revisao": ("revision",),
        "biosInicial": ("initial BIOS version",),
        "biosMinima": ("minimum BIOS version",),
        "biosFlashback": ("BIOS Flashback",),
        "tiposMemoriaSuportados": ("memory support", "DDR"),
        "frequenciasMemoriaJedecMhz": ("JEDEC memory speed",),
        "frequenciasMemoriaOverclockMhz": ("memory overclock", "OC MHz"),
        "capacidadeMaximaMemoriaGb": ("maximum memory",),
        "capacidadeMaximaPorSlotGb": ("maximum memory per slot",),
        "slotsMemoria": ("DIMM slots",),
        "suportaXmp": ("XMP support",),
        "suportaExpo": ("EXPO support",),
        "slotsM2": ("M.2 slots",),
        "portasSata": ("SATA ports",),
        "versaoPcie": ("PCIe version",),
        "wifi": ("Wi-Fi",),
        "bluetooth": ("Bluetooth",),
        "ethernet": ("LAN ethernet controller",),
        "saidasVideo": ("display outputs",),
    },
    "MEMORIA_RAM": {
        "tipo": ("DDR type",),
        "formato": ("DIMM SO-DIMM",),
        "capacidadePorModuloGb": ("capacity per module",),
        "quantidadeModulos": ("kit modules",),
        "frequenciaMhz": ("memory speed",),
        "frequenciaJedecMhz": ("JEDEC speed",),
        "latenciaCl": ("CAS latency CL",),
        "tensaoVolts": ("voltage",),
        "ecc": ("ECC",),
        "registrada": ("registered buffered",),
        "suportaXmp": ("XMP",),
        "suportaExpo": ("EXPO",),
    },
    "ARMAZENAMENTO": {
        "tipo": ("SSD HDD type",),
        "capacidadeGb": ("capacity",),
        "interface": ("interface NVMe SATA",),
        "formato": ("form factor",),
        "geracaoPcie": ("PCIe generation",),
        "pistasPcie": ("PCIe lanes",),
        "leituraSequencialMbps": ("sequential read",),
        "escritaSequencialMbps": ("sequential write",),
        "tamanhoM2Mm": ("M.2 size",),
        "possuiDissipador": ("heatsink",),
    },
    "FONTE": {
        "formato": ("PSU form factor",),
        "potenciaWatts": ("wattage",),
        "certificacao": ("80 Plus certification",),
        "modularidade": ("modular",),
        "padraoAtx": ("ATX version",),
        "eficienciaPercentual": ("efficiency",),
        "comprimentoMm": ("dimensions length",),
        "conectoresAtx24Pinos": ("24 pin ATX",),
        "conectoresEpsCpu": ("EPS CPU connectors",),
        "conectoresPcie8Pinos": ("PCIe 8 pin connectors",),
        "conectores12vhpwr": ("12VHPWR",),
        "conectores12v2x6": ("12V-2x6",),
        "protecoes": ("protections OCP OVP SCP OTP",),
    },
    "GABINETE": {
        "tamanho": ("case size",),
        "alturaMm": ("dimensions height",),
        "larguraMm": ("dimensions width",),
        "profundidadeMm": ("dimensions depth",),
        "formatosPlacaMaeSuportados": ("motherboard support",),
        "comprimentoMaximoGpuMm": ("GPU clearance",),
        "alturaMaximaCoolerCpuMm": ("CPU cooler clearance",),
        "formatosFonteSuportados": ("PSU support",),
        "comprimentoMaximoFonteMm": ("PSU clearance",),
        "slotsTraseiros": ("expansion slots",),
        "suportesFans": ("fan support",),
        "suportesRadiador": ("radiator support",),
        "suportaGpuVertical": ("vertical GPU",),
    },
    "COOLER": {
        "tipo": ("cooler type",),
        "socketsSuportados": ("socket compatibility",),
        "alturaMm": ("height",),
        "capacidadeTermicaWatts": ("TDP capacity",),
        "tamanhoVentoinhaMm": ("fan size",),
        "velocidadeMaxRpm": ("RPM",),
        "fluxoArCfm": ("airflow CFM",),
        "ruidoDb": ("noise dBA",),
        "tamanhoRadiadorMm": ("radiator size",),
    },
    "VENTOINHA": {
        "tamanhoMm": ("fan size",),
        "rpmMaxima": ("max RPM",),
        "rpmMinima": ("min RPM",),
        "fluxoArCfm": ("airflow CFM",),
        "pressaoEstaticaMmH2o": ("static pressure",),
        "ruidoDb": ("noise dBA",),
        "conector": ("connector",),
        "pwm": ("PWM",),
    },
}


def _humanize(field: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(field or "")).replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def build_focus_terms(
    category: str,
    missing_fields: Iterable[str],
    *,
    limit: int = 10,
) -> tuple[str, ...]:
    """Converte lacunas do DTO em termos curtos de pesquisa técnica.

    Os termos são usados apenas para localizar páginas técnicas mais relevantes.
    Eles não viram valores do payload e não relaxam a validação de identidade.
    """
    category = str(category or "").strip().upper()
    mapping = _FIELD_TERMS.get(category, {})
    output: list[str] = []
    seen: set[str] = set()

    for field in missing_fields or ():
        terms = mapping.get(str(field)) or ((_humanize(str(field)),) if field else ())
        for term in terms:
            value = str(term or "").strip()
            key = value.casefold()
            if not value or key in seen:
                continue
            seen.add(key)
            output.append(value)
            if len(output) >= max(1, int(limit)):
                return tuple(output)
    return tuple(output)


def build_focused_queries(
    base_query: str,
    category: str,
    missing_fields: Iterable[str],
    *,
    max_queries: int = 1,
    terms_per_query: int = 4,
) -> tuple[str, ...]:
    base = str(base_query or "").strip()
    if not base:
        return ()
    terms = list(build_focus_terms(category, missing_fields))
    if not terms:
        return (base,)

    output: list[str] = []
    count = max(1, min(2, int(max_queries)))
    chunk_size = max(1, min(5, int(terms_per_query)))
    for offset in range(0, min(len(terms), count * chunk_size), chunk_size):
        chunk = terms[offset : offset + chunk_size]
        output.append(f"{base} {' '.join(chunk)}".strip())
    if base not in output:
        output.append(base)
    return tuple(output)
