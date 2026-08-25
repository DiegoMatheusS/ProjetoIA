import re
import unicodedata

from ..utils.normalizers import clean_text


def normalize_key(value):
    value = clean_text(value)
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def attribute_value(attr):
    value = clean_text(attr.get("value_name"))
    if value:
        return value
    for row in attr.get("values") or []:
        value = clean_text(row.get("name") or row.get("value_name"))
        if value:
            return value
    return None


def attrs_map(attributes):
    out = {}
    for attr in attributes or []:
        value = attribute_value(attr)
        if not value:
            continue
        for key in (attr.get("id"), attr.get("name")):
            normalized = normalize_key(key)
            if normalized and normalized not in out:
                out[normalized] = value
    return out


def find_attr(mapping, *aliases):
    normalized_aliases = [normalize_key(alias) for alias in aliases if alias]

    # Primeiro, correspondência exata.
    for alias in normalized_aliases:
        value = mapping.get(alias)
        if value:
            return value

    # Depois, correspondência parcial controlada. Isso ajuda quando o Mercado
    # Livre varia "Quantidade de núcleos" / "Quantidade de núcleos do processador".
    for alias in normalized_aliases:
        if len(alias) < 5:
            continue
        for key, value in mapping.items():
            if alias in key or key in alias:
                return value

    return None


def number(value, pattern=r"([0-9]+(?:[.,][0-9]+)?)"):
    if not value:
        return None
    match = re.search(pattern, str(value))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def integer(value):
    n = number(value)
    return int(n) if n is not None else None


def frequency_mhz(value):
    n = number(value)
    if n is None:
        return None
    text = str(value).casefold()
    if "ghz" in text:
        return int(round(n * 1000))
    if "mhz" in text:
        return int(round(n))
    # Frequências de CPU abaixo de 20 sem unidade quase sempre estão em GHz.
    if n < 20:
        return int(round(n * 1000))
    return int(round(n))


def size_mb(value):
    n = number(value)
    if n is None:
        return None
    text = str(value).casefold()
    if "kb" in text:
        return round(n / 1024, 3)
    if "gb" in text:
        return round(n * 1024, 3)
    return n


def bool_value(value):
    if value is None:
        return None
    text = normalize_key(value)
    yes = {"sim", "yes", "si", "true", "possui", "incluido", "incluso"}
    no = {"nao", "no", "false", "sem", "nao_possui"}
    if text in yes:
        return True
    if text in no:
        return False
    if text.startswith("com_"):
        return True
    if text.startswith("sem_"):
        return False
    return None


def memory_types(value):
    if not value:
        return []
    found = re.findall(r"\bDDR\s*([345])\b", str(value).upper())
    return list(dict.fromkeys(f"DDR{x}" for x in found))


def title_integer(text, label_pattern):
    if not text:
        return None
    match = re.search(label_pattern, text, re.I)
    return int(match.group(1)) if match else None


def extract_processor_specs(mapping, context_text=""):
    specs = {}

    socket = find_attr(
        mapping,
        "CPU_SOCKET",
        "PROCESSOR_SOCKET",
        "SOCKET_TYPE",
        "SOCKET",
        "Socket",
        "Soquete",
        "Tipo de socket",
        "Tipo de soquete",
    )
    if socket:
        specs["socket"] = re.sub(
            r"^(socket|soquete)\s*", "", socket, flags=re.I
        ).strip().upper()

    family = find_attr(
        mapping, "PROCESSOR_FAMILY", "CPU_FAMILY", "FAMILY", "Família do processador"
    )
    if family:
        specs["familia"] = family

    line = find_attr(
        mapping, "LINE", "PROCESSOR_LINE", "Linha", "Linha do processador"
    )
    if line:
        specs["linha"] = line

    generation = find_attr(
        mapping, "PROCESSOR_GENERATION", "GENERATION", "Geração", "Geração do processador"
    )
    if generation:
        specs["geracao"] = generation

    architecture = find_attr(
        mapping,
        "PROCESSOR_ARCHITECTURE",
        "CPU_ARCHITECTURE",
        "ARCHITECTURE",
        "Arquitetura",
        "Microarquitetura",
    )
    if architecture:
        specs["arquitetura"] = architecture

    lithography = integer(find_attr(
        mapping,
        "LITHOGRAPHY",
        "PROCESSOR_LITHOGRAPHY",
        "CPU_LITHOGRAPHY",
        "Litografia",
        "Processo de fabricação",
    ))
    if lithography is not None:
        specs["litografiaNm"] = lithography

    cores = integer(find_attr(
        mapping,
        "PROCESSOR_CORES_NUMBER",
        "CPU_CORES_NUMBER",
        "CORES_NUMBER",
        "Quantidade de núcleos do processador",
        "Quantidade de núcleos",
        "Número de núcleos",
    ))
    if cores is None:
        cores = title_integer(context_text, r"(\d+)\s*n[uú]cleos")
    if cores is not None:
        specs["nucleos"] = cores

    threads = integer(find_attr(
        mapping,
        "PROCESSOR_THREADS_NUMBER",
        "CPU_THREADS_NUMBER",
        "THREADS_NUMBER",
        "Quantidade de threads do processador",
        "Quantidade de threads",
        "Número de threads",
    ))
    if threads is None:
        threads = title_integer(context_text, r"(\d+)\s*threads")
    if threads is not None:
        specs["threads"] = threads

    base = frequency_mhz(find_attr(
        mapping,
        "PROCESSOR_BASE_FREQUENCY",
        "CPU_BASE_FREQUENCY",
        "BASE_CLOCK_FREQUENCY",
        "BASE_FREQUENCY",
        "Frequência base",
        "Frequência básica",
        "Clock base",
    ))
    if base is not None:
        specs["frequenciaBaseMhz"] = base

    turbo = frequency_mhz(find_attr(
        mapping,
        "MAX_TURBO_FREQUENCY",
        "PROCESSOR_MAX_FREQUENCY",
        "CPU_MAX_FREQUENCY",
        "MAX_CLOCK_FREQUENCY",
        "Frequência turbo máxima",
        "Frequência máxima",
        "Clock máximo",
        "Clock turbo",
    ))
    if turbo is not None:
        specs["frequenciaTurboMhz"] = turbo

    cache_l2 = size_mb(find_attr(
        mapping, "L2_CACHE", "CACHE_L2", "PROCESSOR_L2_CACHE", "Cache L2", "Memória cache L2"
    ))
    if cache_l2 is not None:
        specs["cacheL2Mb"] = cache_l2

    cache_l3 = size_mb(find_attr(
        mapping, "L3_CACHE", "CACHE_L3", "PROCESSOR_L3_CACHE", "Cache L3", "Memória cache L3"
    ))
    if cache_l3 is not None:
        specs["cacheL3Mb"] = cache_l3

    tdp = integer(find_attr(
        mapping,
        "THERMAL_DESIGN_POWER",
        "PROCESSOR_TDP",
        "TDP",
        "Potência de design térmico",
        "Potência térmica",
    ))
    if tdp is not None:
        specs["tdpWatts"] = tdp

    memory = find_attr(
        mapping,
        "RAM_MEMORY_TYPE",
        "SUPPORTED_RAM_MEMORY_TYPES",
        "SUPPORTED_MEMORY_TYPES",
        "MEMORY_TYPE",
        "Tipos de memória RAM suportados",
        "Tipo de memória RAM",
        "Tipo de memória",
    )
    types = memory_types(memory)
    if types:
        specs["tiposMemoriaSuportados"] = types

    memory_frequency = frequency_mhz(find_attr(
        mapping,
        "MAX_RAM_MEMORY_FREQUENCY",
        "MAX_MEMORY_FREQUENCY",
        "MEMORY_SPEED",
        "Frequência máxima da memória",
        "Velocidade máxima da memória",
    ))
    if memory_frequency is not None:
        specs["frequenciaMemoriaMaximaMhz"] = memory_frequency

    max_memory = integer(find_attr(
        mapping,
        "MAX_RAM_MEMORY_CAPACITY",
        "MAX_MEMORY_CAPACITY",
        "Capacidade máxima de memória RAM",
        "Capacidade máxima de memória",
    ))
    if max_memory is not None:
        specs["capacidadeMemoriaMaximaGb"] = max_memory

    channels = integer(find_attr(
        mapping,
        "MEMORY_CHANNELS_NUMBER",
        "MEMORY_CHANNELS",
        "Quantidade de canais de memória",
        "Canais de memória",
    ))
    if channels is not None:
        specs["canaisMemoria"] = channels

    ecc = bool_value(find_attr(
        mapping, "WITH_ECC", "ECC_SUPPORT", "Suporta ECC", "Com ECC"
    ))
    if ecc is not None:
        specs["suportaEcc"] = ecc

    max_temp = number(find_attr(
        mapping,
        "MAX_OPERATING_TEMPERATURE",
        "MAX_TEMPERATURE",
        "Temperatura máxima",
        "Temperatura máxima de operação",
    ))
    if max_temp is not None:
        specs["temperaturaMaximaC"] = max_temp

    pcie = find_attr(
        mapping,
        "PCIE_VERSION",
        "PCI_EXPRESS_VERSION",
        "PCI_E_VERSION",
        "Versão PCI Express",
        "Versão PCIe",
    )
    if pcie:
        match = re.search(r"(\d+(?:[.,]\d+)?)", pcie)
        specs["versaoPcie"] = match.group(1).replace(",", ".") if match else pcie

    lanes = integer(find_attr(
        mapping,
        "PCIE_LANES_NUMBER",
        "PCI_EXPRESS_LANES_NUMBER",
        "Quantidade de pistas PCIe",
        "Lanes PCIe",
    ))
    if lanes is not None:
        specs["lanesPcie"] = lanes

    integrated_model = find_attr(
        mapping,
        "INTEGRATED_GRAPHICS_MODEL",
        "INTEGRATED_GRAPHICS",
        "GPU_MODEL",
        "Modelo de gráficos integrado",
        "Modelo da GPU integrada",
        "Gráficos integrados",
    )
    integrated_bool = bool_value(find_attr(
        mapping,
        "WITH_INTEGRATED_GRAPHICS",
        "HAS_INTEGRATED_GRAPHICS",
        "Com gráficos integrados",
        "Possui gráficos integrados",
    ))
    if integrated_model:
        specs["possuiVideoIntegrado"] = True
        specs["modeloVideoIntegrado"] = integrated_model
    elif integrated_bool is not None:
        specs["possuiVideoIntegrado"] = integrated_bool

    cooler = bool_value(find_attr(
        mapping,
        "INCLUDES_CPU_COOLER",
        "COOLER_INCLUDED",
        "Inclui cooler",
        "Cooler incluso",
    ))
    if cooler is not None:
        specs["coolerIncluso"] = cooler

    unlocked = bool_value(find_attr(
        mapping,
        "UNLOCKED_MULTIPLIER",
        "MULTIPLIER_UNLOCKED",
        "Multiplicador desbloqueado",
    ))
    if unlocked is not None:
        specs["multiplicadorDesbloqueado"] = unlocked

    overclock = bool_value(find_attr(
        mapping,
        "SUPPORTS_OVERCLOCK",
        "OVERCLOCK_SUPPORT",
        "Suporta overclock",
    ))
    if overclock is not None:
        specs["suporteOverclock"] = overclock

    release = find_attr(
        mapping, "RELEASE_DATE", "LAUNCH_DATE", "Data de lançamento"
    )
    if release:
        specs["dataLancamento"] = release

    return specs


def extract_specs(category: str | None, attributes, context_text=""):
    if not category:
        return {}

    mapping = attrs_map(attributes)

    if category == "PROCESSADOR":
        return extract_processor_specs(mapping, context_text=context_text)

    specs = {}

    if category == "TECLADO":
        switch = find_attr(
            mapping, "KEYBOARD_SWITCH", "Switch", "Tipo de switch"
        )
        layout = find_attr(mapping, "KEYBOARD_LAYOUT", "Layout")
        connection = find_attr(
            mapping, "CONNECTION_TYPE", "Tipo de conexão", "Conectividade"
        )
        if switch:
            specs["switch"] = switch
        if layout:
            specs["layout"] = layout
        if connection:
            specs["conexao"] = connection
            connection_key = normalize_key(connection)
            specs["usb"] = "usb" in connection_key
            specs["bluetooth"] = "bluetooth" in connection_key
            specs["wireless"] = any(
                x in connection_key for x in ("wireless", "sem_fio", "2_4")
            )

    return specs
