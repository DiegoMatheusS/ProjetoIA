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
    for item in attributes or []:
        value = attribute_value(item)
        if not value:
            continue
        for key in (item.get("id"), item.get("name")):
            normalized = normalize_key(key)
            if normalized and normalized not in out:
                out[normalized] = value
    return out


def attr(mapping, *aliases):
    # Correspondência exata normalizada. Não usamos contains/fuzzy em dados técnicos.
    for alias in aliases:
        value = mapping.get(normalize_key(alias))
        if value:
            return value
    return None


def first_match(text, *patterns, flags=re.I):
    for pattern in patterns:
        match = re.search(pattern, text or "", flags)
        if match:
            return clean_text(match.group(1))
    return None


def number(value):
    if value is None:
        return None
    match = re.search(r"(-?[0-9]+(?:[.,][0-9]+)?)", str(value))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def integer(value):
    value = number(value)
    return int(round(value)) if value is not None else None


def frequency_mhz(value):
    n = number(value)
    if n is None:
        return None
    text = str(value).casefold()
    if "ghz" in text:
        return int(round(n * 1000))
    if "mhz" in text:
        return int(round(n))
    return int(round(n * 1000 if n < 20 else n))


def capacity_gb(value):
    n = number(value)
    if n is None:
        return None
    text = str(value).casefold()
    if "tb" in text:
        return int(round(n * 1024))
    if "mb" in text:
        return int(round(n / 1024))
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


def boolean(value):
    if value is None:
        return None
    raw = str(value).strip()
    if raw in {"✓", "✔", "✅"}:
        return True
    if raw in {"✗", "✘", "❌"}:
        return False
    token = normalize_key(value)
    yes = {"sim", "yes", "true", "possui", "incluso", "incluido", "com", "compativel"}
    no = {"nao", "no", "false", "sem", "nao_possui", "nao_incluso", "nao_incluido"}
    if token in yes:
        return True
    if token in no:
        return False
    return None


def memory_types(value):
    if not value:
        return []
    found = re.findall(r"\bDDR\s*([345])\b", str(value).upper())
    return list(dict.fromkeys(f"DDR{x}" for x in found))


def unique(values):
    return list(dict.fromkeys(v for v in values if v not in (None, "", [])))


def set_if(specs, key, value):
    if value not in (None, "", []):
        specs[key] = value


def text_number(text, *patterns):
    value = first_match(text, *patterns, flags=re.I | re.S)
    return number(value)


def text_integer(text, *patterns):
    value = text_number(text, *patterns)
    return int(round(value)) if value is not None else None


def text_frequency(text, *patterns):
    value = first_match(text, *patterns, flags=re.I | re.S)
    return frequency_mhz(value)


def text_capacity(text, *patterns):
    value = first_match(text, *patterns, flags=re.I | re.S)
    return capacity_gb(value)


def explicit_keyword_bool(text, positive_patterns=(), negative_patterns=()):
    for pattern in negative_patterns:
        if re.search(pattern, text or "", re.I):
            return False
    for pattern in positive_patterns:
        if re.search(pattern, text or "", re.I):
            return True
    return None


def normalize_cpu_socket(value):
    value = clean_text(value)
    if not value:
        return None
    # Intel pode publicar FCLGA1700 / LGA 1700; o backend usa LGA1700.
    m = re.search(r"(?:FC)?LGA\s*(\d{3,4})", value, re.I)
    if m:
        return f"LGA{m.group(1)}"
    m = re.search(r"\b(AM[2345]|TR4|sTRX4|sTR5|sWRX8)\b", value, re.I)
    if m:
        return m.group(1).upper()
    value = re.sub(r"^(?:socket|soquete)\s*", "", value, flags=re.I)
    return re.sub(r"\s+", "", value).upper() or None


def normalize_form_factor(value):
    token = normalize_key(value)
    if not token:
        return None
    if "mini_itx" in token or token == "itx":
        return "MINI_ITX"
    if "micro_atx" in token or "microatx" in token or token in {"matx", "m_atx"}:
        return "MICRO_ATX"
    if "e_atx" in token or "eatx" in token or "extended_atx" in token:
        return "E_ATX"
    if token == "atx" or "formato_atx" in token or token.startswith("atx_"):
        return "ATX"
    return None


def normalize_psu_format(value):
    token = normalize_key(value)
    if not token:
        return None
    if "sfx_l" in token or "sfxl" in token:
        return "SFX_L"
    if token == "sfx" or "formato_sfx" in token:
        return "SFX"
    if "flex_atx" in token:
        return "FLEX_ATX"
    if token == "tfx" or "formato_tfx" in token:
        return "TFX"
    if token == "atx" or "formato_atx" in token or token.startswith("atx_") or "_atx_" in token:
        return "ATX"
    return None


def normalize_case_size(value):
    token = normalize_key(value)
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


def normalize_storage_format(value):
    token = normalize_key(value)
    if not token:
        return None
    if "m_2" in token or token == "m2" or re.search(r"\b22(?:30|42|60|80|110)\b", str(value)):
        return "M2"
    if "2_5" in token or "2_5_polegadas" in token:
        return "POLEGADAS_2_5"
    if "3_5" in token or "3_5_polegadas" in token:
        return "POLEGADAS_3_5"
    if "pcie" in token and ("placa" in token or "add_in" in token):
        return "PLACA_PCIE"
    return None


def normalize_storage_interface(value):
    raw = clean_text(value)
    if not raw:
        return None
    # Usa termos técnicos completos. Procurar simplesmente "sas" em texto
    # normalizado gera falsos positivos dentro de palavras comuns da página.
    if re.search(r"\bNVMe\b", raw, re.I) or (re.search(r"\bPCIe?\b|PCI\s*Express", raw, re.I) and not re.search(r"\bSATA\b", raw, re.I)):
        return "NVME_PCIE"
    if re.search(r"\bSAS\b", raw, re.I):
        return "SAS"
    if re.search(r"\bSATA\b", raw, re.I):
        return "SATA"
    return None


def connector_fan(value):
    token = normalize_key(value)
    if "4_pinos" in token or "4_pin" in token or "pwm" in token:
        return "PWM_4_PINOS"
    if "3_pinos" in token or "3_pin" in token:
        return "DC_3_PINOS"
    if "molex" in token:
        return "MOLEX"
    if token and "propriet" in token:
        return "PROPRIETARIO"
    return None


def ports_count(text, token_pattern):
    # Conta apenas quando a quantidade aparece explicitamente como quantidade
    # de portas/conectores. Versões como HDMI 2.1 e DP 1.4 NÃO são contagens.
    patterns = [
        rf"(\d+)\s*(?:[xX]\s*)?{token_pattern}",
        rf"(?:quantidade\s+de\s+|portas?\s+|conectores?\s+){token_pattern}\s*[:x-]?\s*(\d+)",
        rf"{token_pattern}\s*[:x-]\s*(\d+)\s*(?:portas?|conectores?)",
    ]
    for pattern in patterns:
        value = first_match(text, pattern)
        if value:
            return int(value)
    return None


def grouped_integer(value):
    """Inteiro técnico com separadores de milhar pt-BR/en (6.000 -> 6000)."""
    if value is None:
        return None
    match = re.search(r"-?[0-9][0-9.,]*", str(value))
    if not match:
        return None
    token = match.group(0)
    # 6.000 / 2.000.000 / 6,000 são quase sempre agrupamentos quando o
    # resultado esperado é inteiro técnico (MB/s, MTBF, RPM etc.).
    if re.fullmatch(r"-?\d{1,3}(?:[.,]\d{3})+", token):
        token = re.sub(r"[.,]", "", token)
    elif "," in token and "." in token:
        # usa o último separador como decimal, remove o outro como milhar
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    else:
        token = token.replace(",", ".")
    try:
        return int(round(float(token)))
    except ValueError:
        return None


def dimension_value_mm(value):
    if value is None:
        return None
    n = number(value)
    if n is None:
        return None
    text = str(value).casefold()
    if "cm" in text:
        return round(n * 10, 3)
    if "mm" in text:
        return n
    if re.search(r"(?:^|\s)m(?:$|\s)", text):
        return round(n * 1000, 3)
    return n


def dimension_triplet_mm(value):
    """Retorna três dimensões em mm quando a ordem está explicitamente dada."""
    if not value:
        return None
    pat = re.compile(
        r"([0-9]+(?:[.,][0-9]+)?)\s*(mm|cm)?\s*[x×]\s*"
        r"([0-9]+(?:[.,][0-9]+)?)\s*(mm|cm)?\s*[x×]\s*"
        r"([0-9]+(?:[.,][0-9]+)?)\s*(mm|cm)?",
        re.I,
    )
    m = pat.search(str(value))
    if not m:
        return None
    vals=[]
    groups=[(m.group(1),m.group(2)),(m.group(3),m.group(4)),(m.group(5),m.group(6))]
    fallback_unit=next((u for _,u in groups if u), "mm")
    for raw,unit in groups:
        n=number(raw)
        if n is None:
            return None
        unit=(unit or fallback_unit).casefold()
        vals.append(round(n*10,3) if unit=="cm" else n)
    return tuple(vals)


def labeled_dimension_mm(text, label):
    raw = first_match(text or "", rf"{label}\s*:?\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mm|cm))")
    return dimension_value_mm(raw)

def resolution(value):
    if not value:
        return None
    match = re.search(r"(\d{3,5})\s*[x×]\s*(\d{3,5})", str(value), re.I)
    if match:
        return f"{match.group(1)}x{match.group(2)}"
    token = str(value).upper()
    labels = ["4K", "UHD", "QHD", "WQHD", "FHD", "FULL HD", "HD"]
    for label in labels:
        if label in token:
            return label
    return clean_text(value)


def extract_processor(mapping, text):
    specs = {}
    socket_raw = attr(mapping, "CPU_SOCKET", "PROCESSOR_SOCKET", "SOCKET", "Socket", "Soquete", "Soquetes compatíveis", "Soquetes compativeis", "Sockets Supported") or first_match(text, r"(?:Socket|Soquete)\s*:\s*([A-Za-z0-9+\-]+)")
    set_if(specs, "socket", normalize_cpu_socket(socket_raw))
    family_attr = attr(mapping, "PROCESSOR_FAMILY", "CPU_FAMILY", "Família do processador", "Family")
    if family_attr:
        # CPU-Monkey costuma usar "Intel Core i5"/"AMD Ryzen 5" em Family.
        # Mantemos a família completa quando ela é explicitamente rotulada.
        set_if(specs, "familia", family_attr)
    set_if(specs, "linha", attr(mapping, "LINE", "PROCESSOR_LINE", "Linha do processador", "CPU group"))
    set_if(specs, "geracao", attr(mapping, "PROCESSOR_GENERATION", "Geração do processador", "Generation"))

    architecture = attr(mapping, "MICROARCHITECTURE", "PROCESSOR_MICROARCHITECTURE", "Microarquitetura", "Arquitetura", "Architecture")
    if architecture and normalize_key(architecture) not in {"x86_64", "x64", "amd64", "x86", "ia_32"}:
        specs["arquitetura"] = architecture

    set_if(specs, "litografiaNm", integer(attr(mapping, "LITHOGRAPHY", "PROCESSOR_LITHOGRAPHY", "Litografia", "Processo de fabricação", "Lithography", "Technology")))
    set_if(specs, "nucleos", integer(attr(mapping, "PROCESSOR_CORES_NUMBER", "CPU_CORES_NUMBER", "CORES_NUMBER", "Quantidade de núcleos do processador", "Número de núcleos", "Total Cores", "Cores", "Core Count")))
    set_if(specs, "threads", integer(attr(mapping, "PROCESSOR_THREADS_NUMBER", "THREADS_NUMBER", "Quantidade de threads do processador", "Número de threads", "Total Threads", "Threads", "Thread Count")))
    cores_threads = attr(mapping, "CPU Cores / Threads", "Cores / Threads")
    if cores_threads:
        pair = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})", cores_threads)
        if pair:
            if "nucleos" not in specs:
                specs["nucleos"] = int(pair.group(1))
            if "threads" not in specs:
                specs["threads"] = int(pair.group(2))
    set_if(specs, "frequenciaBaseMhz", frequency_mhz(attr(mapping, "PROCESSOR_BASE_FREQUENCY", "BASE_CLOCK_FREQUENCY", "Frequência base", "Clock base", "Processor Base Frequency", "Base Frequency", "Base Clock", "Frequency")))
    set_if(specs, "frequenciaTurboMhz", frequency_mhz(attr(mapping, "MAX_TURBO_FREQUENCY", "PROCESSOR_MAX_FREQUENCY", "Frequência turbo máxima", "Frequência máxima", "Max Turbo Frequency", "Maximum Turbo Frequency", "Turbo Frequency (1 Core)", "Turbo Frequency", "Boost Clock")))
    set_if(specs, "cacheL2Mb", size_mb(attr(mapping, "L2_CACHE", "PROCESSOR_L2_CACHE", "Cache L2", "L2-Cache", "L2 Cache")))
    set_if(specs, "cacheL3Mb", size_mb(attr(mapping, "L3_CACHE", "PROCESSOR_L3_CACHE", "Cache L3", "L3-Cache", "L3 Cache", "Intel Smart Cache", "Cache")))
    set_if(specs, "tdpWatts", integer(attr(mapping, "THERMAL_DESIGN_POWER", "PROCESSOR_TDP", "TDP", "Thermal Design Power")))

    mem = attr(mapping, "RAM_MEMORY_TYPE", "SUPPORTED_RAM_MEMORY_TYPES", "Tipos de memória RAM suportados", "Tipos de memória RAM suportadas", "Tipo de memória RAM", "Tipo de Memória", "Memory Types", "Supported Memory Types", "Memory type")
    if memory_types(mem):
        specs["tiposMemoriaSuportados"] = memory_types(mem)
    set_if(specs, "frequenciaMemoriaMaximaMhz", frequency_mhz(attr(mapping, "MAX_RAM_MEMORY_FREQUENCY", "MAX_MEMORY_FREQUENCY", "Frequência máxima da memória", "Max Memory Frequency")))
    # Em Intel ARK e CPU-Monkey a velocidade costuma vir embutida em DDR4-2666/DDR5-5600.
    if "frequenciaMemoriaMaximaMhz" not in specs and mem:
        mem_clock = first_match(mem, r"DDR[345]\s*[- ]\s*(\d{3,5})")
        set_if(specs, "frequenciaMemoriaMaximaMhz", integer(mem_clock))
    set_if(specs, "capacidadeMemoriaMaximaGb", capacity_gb(attr(mapping, "MAX_RAM_MEMORY_CAPACITY", "MAX_MEMORY_CAPACITY", "Capacidade máxima de memória", "Max Memory Size (dependent on memory type)", "Max Memory Size", "Max. Memory", "Maximum Memory")))
    set_if(specs, "canaisMemoria", integer(attr(mapping, "MEMORY_CHANNELS_NUMBER", "MEMORY_CHANNELS", "Canais de memória", "Max # of Memory Channels", "Memory channels")))
    set_if(specs, "suportaEcc", boolean(attr(mapping, "ECC_SUPPORT", "WITH_ECC", "Suporta ECC", "ECC Memory Supported", "ECC")))
    set_if(specs, "temperaturaMaximaC", number(attr(mapping, "MAX_OPERATING_TEMPERATURE", "MAX_TEMPERATURE", "Temperatura máxima", "T_JUNCTION", "T. junction max.")))
    pcie = attr(mapping, "PCIE_VERSION", "PCI_EXPRESS_VERSION", "Versão PCI Express", "Versão PCIe", "Interface", "PCI Express Revision", "PCIe")
    if pcie:
        set_if(specs, "versaoPcie", first_match(pcie, r"(\d+(?:[.,]\d+)?)") or pcie)
    set_if(specs, "lanesPcie", integer(attr(mapping, "PCIE_LANES_NUMBER", "PCI_EXPRESS_LANES_NUMBER", "Lanes PCIe", "Max # of PCI Express Lanes")))
    if "lanesPcie" not in specs and pcie:
        lanes = first_match(pcie, r"(?:x|×)\s*(\d{1,2})\b")
        set_if(specs, "lanesPcie", integer(lanes))
    cooler_incluso = boolean(attr(mapping, "COOLER_INCLUDED", "INCLUDES_CPU_COOLER", "Cooler incluso"))
    if cooler_incluso is None:
        cooler_incluso = explicit_keyword_bool(
            text,
            positive_patterns=(r"\bcom\s+cooler\b", r"\bcooler\s+inclus[oa]\b"),
            negative_patterns=(r"\bsem\s+cooler\b", r"\bS(?:/|\s)\s*Cooler\b"),
        )
    set_if(specs, "coolerIncluso", cooler_incluso)
    set_if(specs, "multiplicadorDesbloqueado", boolean(attr(mapping, "UNLOCKED_MULTIPLIER", "Multiplicador desbloqueado", "Unlocked Multiplier", "Multiplier unlocked")))
    set_if(specs, "suporteOverclock", boolean(attr(mapping, "OVERCLOCK_SUPPORT", "Suporta overclock", "Overclocking", "Overclock Support")))
    set_if(specs, "dataLancamento", attr(mapping, "RELEASE_DATE", "LAUNCH_DATE", "Data de lançamento", "Launch Date", "Release date"))

    # Vídeo integrado explícito em fontes técnicas em inglês.
    gpu_name = attr(mapping, "Processor Graphics", "Integrated Graphics", "GPU name", "iGPU")
    if gpu_name and "possuiVideoIntegrado" not in specs:
        low_gpu = normalize_key(gpu_name)
        if low_gpu in {"no_igpu", "no_integrated_graphics", "none", "nao", "no"} or "no_igpu" in low_gpu:
            specs["possuiVideoIntegrado"] = False
        else:
            specs["possuiVideoIntegrado"] = True
            specs["modeloVideoIntegrado"] = clean_text(gpu_name)
    if "possuiVideoIntegrado" not in specs:
        integrated_en = explicit_keyword_bool(
            text,
            positive_patterns=(r"\bintegrated\s+graphics\s*:?\s*(?!no\b|none\b)[A-Za-z0-9]", r"\bprocessor\s+graphics\s*:?\s*(?!no\b|none\b)[A-Za-z0-9]"),
            negative_patterns=(r"\bwithout\s+(?:an\s+)?integrated\s+graphics(?:\s+unit)?\b", r"\bno\s+iGPU\b", r"\bintegrated\s+graphics\s*:?\s*(?:no|none)\b"),
        )
        set_if(specs, "possuiVideoIntegrado", integrated_en)

    # Complementos explícitos no título/ficha. Estes padrões só rodam depois
    # que a categoria já foi identificada como PROCESSADOR.
    if "socket" not in specs:
        set_if(specs, "socket", normalize_cpu_socket(first_match(text, r"\b(AM[345]|(?:FC)?LGA\s*\d{3,4}|sTRX4|TR4|sWRX8)\b")))
    if "nucleos" not in specs:
        set_if(specs, "nucleos", text_integer(text, r"\b(\d{1,3})\s+n[uú]cleos?\b"))
    if "threads" not in specs:
        set_if(specs, "threads", text_integer(text, r"\b(\d{1,3})\s+threads?\b"))
    if "frequenciaTurboMhz" not in specs:
        set_if(specs, "frequenciaTurboMhz", text_frequency(text, r"\b([0-9.,]+\s*(?:GHz|MHz))\s+(?:Max\s+Turbo|Turbo\s+M[aá]x(?:imo)?)\b"))
    if "possuiVideoIntegrado" not in specs:
        integrated = explicit_keyword_bool(
            text,
            positive_patterns=(r"\bv[ií]deo\s+integrado\b", r"\bgr[aá]ficos?\s+integrados?\b"),
            negative_patterns=(
                r"\bsem\s+v[ií]deo\s+integrado\b",
                r"\bn[aã]o\s+possui\s+v[ií]deo\s+integrado\b",
                r"\bsem\s+gr[aá]ficos?\s+integrados?\b",
                r"\bS(?:/|\s)\s*V[ií]deo\b",
            ),
        )
        set_if(specs, "possuiVideoIntegrado", integrated)

    # Complementos apenas com rótulos explícitos na descrição.
    set_if(specs, "nucleos", text_integer(text, r"(?:N[ºo°]\s*de\s*n[uú]cleos(?:\s*de\s*CPU)?|Quantidade\s*de\s*n[uú]cleos)\s*:\s*(\d+)"))
    set_if(specs, "threads", text_integer(text, r"(?:N[ºo°]\s*de\s*threads|Quantidade\s*de\s*threads)\s*:\s*(\d+)"))
    set_if(specs, "frequenciaBaseMhz", text_frequency(text, r"(?:Clock\s+b[aá]sico|Clock\s+base|Frequ[eê]ncia\s+base)\s*:\s*([0-9.,]+\s*(?:GHz|MHz))"))
    set_if(specs, "frequenciaTurboMhz", text_frequency(text, r"(?:Clock\s+de\s+Max\s+Boost|Max\s+Boost|Clock\s+turbo|Frequ[eê]ncia\s+turbo(?:\s+m[aá]xima)?)\s*:\s*(?:At[eé]\s*)?([0-9.,]+\s*(?:GHz|MHz))"))
    l2 = first_match(text, r"Cache\s+L2(?:\s+total)?\s*:\s*([0-9.,]+\s*(?:KB|MB|GB))")
    l3 = first_match(text, r"Cache\s+L3(?:\s+total)?\s*:\s*([0-9.,]+\s*(?:KB|MB|GB))")
    if l2: specs["cacheL2Mb"] = size_mb(l2)
    if l3: specs["cacheL3Mb"] = size_mb(l3)
    set_if(specs, "tdpWatts", text_integer(text, r"(?:TDP(?:\s*/\s*TDP\s*Padr[aã]o)?|Pot[eê]ncia\s+de\s+design\s+t[eé]rmico)\s*:\s*([0-9.,]+)\s*W"))
    if "tiposMemoriaSuportados" not in specs:
        types = memory_types(first_match(text, r"Mem[oó]ria\s*[-:]\s*([^.;\n]+)") or "")
        if types: specs["tiposMemoriaSuportados"] = types
    set_if(specs, "frequenciaMemoriaMaximaMhz", text_frequency(text, r"Mem[oó]ria.{0,100}?Velocidade\s+m[aá]xima\s*:\s*([0-9.,]+\s*(?:MHz|GHz))"))
    set_if(specs, "temperaturaMaximaC", text_number(text, r"(?:Temps?\s+m[aá]x|Temperatura\s+m[aá]xima)\s*:\s*([0-9.,]+)\s*[°º]?\s*C"))
    set_if(specs, "litografiaNm", text_integer(text, r"(?:CMOS|Litografia|Processo\s+de\s+fabrica[cç][aã]o)\s*:\s*[^.;,\-]*?(\d+)\s*nm"))
    if "versaoPcie" not in specs:
        set_if(specs, "versaoPcie", first_match(text, r"(?:Vers[aã]o\s+do\s+PCI\s+Express|Vers[aã]o\s+PCIe?)\s*:\s*PCIe?\s*([0-9.]+)"))
    if "coolerIncluso" not in specs:
        cooler = first_match(text, r"(?:Solu[cç][aã]o\s+t[eé]rmica\s*\(Cooler\)|Cooler\s+incluso|Inclui\s+cooler)\s*:\s*([^\-;\n]+)")
        if cooler:
            specs["coolerIncluso"] = normalize_key(cooler) not in {"nao", "nenhum", "sem", "nao_incluso"}
    if "multiplicadorDesbloqueado" not in specs:
        value = first_match(text, r"\bDesbloqueado\s*:\s*(Sim|N[aã]o)")
        set_if(specs, "multiplicadorDesbloqueado", boolean(value))
    graphical = first_match(text, r"Modelo\s+Gr[aá]fico\s*:\s*([A-Za-z0-9][A-Za-z0-9 .+\-]+?)(?=\s+-\s+|$)")
    if graphical:
        specs["possuiVideoIntegrado"] = True
        specs["modeloVideoIntegrado"] = graphical
    if "familia" not in specs:
        family = first_match(text, r"\b(?:AMD\s+)?(Ryzen)\s+[3579]\b") or first_match(text, r"\b(Intel\s+Core)\s+(?:Ultra\s+)?[3579i]")
        set_if(specs, "familia", family)

    # v14.12: rótulos usados em páginas técnicas em inglês (Intel ARK,
    # CPU-World, CPU-Monkey/WikiChip). Só aceita valores junto a um rótulo
    # explícito, mantendo a regra de não inventar especificações.
    if "litografiaNm" not in specs:
        set_if(specs, "litografiaNm", text_integer(text, r"(?:Lithography|Process(?:\s+Technology)?|Manufacturing\s+Process)\s*:?\s*(\d+)\s*nm"))
    if "nucleos" not in specs:
        set_if(specs, "nucleos", text_integer(text, r"(?:^|\n)\s*(?:Total\s+Cores|Core\s+Count)\s*:?\s*(\d{1,3})(?!\s*(?:GHz|MHz))"))
    if "threads" not in specs:
        set_if(specs, "threads", text_integer(text, r"(?:^|\n)\s*(?:Total\s+Threads|Thread\s+Count)\s*:?\s*(\d{1,3})"))
    if "frequenciaBaseMhz" not in specs:
        set_if(specs, "frequenciaBaseMhz", text_frequency(text, r"(?:Processor\s+Base\s+Frequency|Base\s+Frequency|Base\s+Clock)\s*:?\s*([0-9.,]+\s*(?:GHz|MHz))"))
    if "frequenciaTurboMhz" not in specs:
        set_if(specs, "frequenciaTurboMhz", text_frequency(text, r"(?:Max\s+Turbo\s+Frequency|Maximum\s+Turbo\s+Frequency|Turbo\s+Frequency|Boost\s+Clock)\s*:?\s*([0-9.,]+\s*(?:GHz|MHz))"))
    if "cacheL3Mb" not in specs:
        smart_cache = first_match(text, r"(?:Intel(?:®|\s)*Smart\s+Cache|L3\s+Cache)\s*:?\s*([0-9.,]+\s*(?:KB|MB|GB))")
        if smart_cache:
            specs["cacheL3Mb"] = size_mb(smart_cache)
    if "tdpWatts" not in specs:
        set_if(specs, "tdpWatts", text_integer(text, r"(?:TDP|Thermal\s+Design\s+Power)\s*:?\s*([0-9.,]+)\s*W"))
    if "tiposMemoriaSuportados" not in specs:
        mem_en = first_match(text, r"(?:^|\n)\s*(?:Memory\s+Types?|Supported\s+Memory\s+Types?)\s*:?\s*([^;\n]{1,120})", flags=re.I | re.M)
        types = memory_types(mem_en or "")
        if types:
            specs["tiposMemoriaSuportados"] = types
            if "frequenciaMemoriaMaximaMhz" not in specs:
                mem_freq = first_match(mem_en or "", r"DDR[345]\s*[- ]\s*(\d{3,5})")
                set_if(specs, "frequenciaMemoriaMaximaMhz", integer(mem_freq))
    if "capacidadeMemoriaMaximaGb" not in specs:
        set_if(specs, "capacidadeMemoriaMaximaGb", text_capacity(text, r"(?:Max\s+Memory\s+Size|Maximum\s+Memory(?:\s+Size)?)\s*(?:\([^)]*\))?\s*:?\s*([0-9.,]+\s*(?:GB|TB))"))
    if "canaisMemoria" not in specs:
        set_if(specs, "canaisMemoria", text_integer(text, r"(?:Max\s*#?\s*of\s+Memory\s+Channels|Memory\s+Channels)\s*:?\s*(\d+)"))
    if "suportaEcc" not in specs:
        ecc_en = first_match(text, r"ECC\s+Memory\s+Supported[^A-Za-z]*(Yes|No)")
        set_if(specs, "suportaEcc", boolean(ecc_en))
    if "versaoPcie" not in specs:
        pcie_en = first_match(text, r"(?:PCI\s+Express\s+Revision|PCIe?\s+Version)\s*:?\s*([0-9.]+)")
        set_if(specs, "versaoPcie", pcie_en)
    if "lanesPcie" not in specs:
        set_if(specs, "lanesPcie", text_integer(text, r"(?:Max\s*#?\s*of\s+PCI\s+Express\s+Lanes|PCIe?\s+Lanes)\s*:?\s*(\d+)"))
    if "socket" not in specs:
        socket_en = first_match(text, r"(?:Sockets?\s+Supported|Socket)\s*:?\s*((?:FC)?LGA\s*\d{3,4}|AM[345]|sTRX4|TR4|sWRX8)")
        set_if(specs, "socket", normalize_cpu_socket(socket_en))
    if "temperaturaMaximaC" not in specs:
        set_if(specs, "temperaturaMaximaC", text_number(text, r"(?:T[_ ]?JUNCTION|Tjunction|Maximum\s+Operating\s+Temperature)\s*:?\s*([0-9.,]+)\s*[°º]?\s*C"))
    if "dataLancamento" not in specs:
        set_if(specs, "dataLancamento", first_match(text, r"(?:Launch\s+Date|Release\s+Date)\s*:?\s*([A-Za-z0-9' ./-]{2,30})"))
    if "arquitetura" not in specs:
        codename = first_match(text, r"Code\s+Name\s+(?:Products\s+formerly\s+)?([A-Za-z][A-Za-z0-9 -]{2,40}?)(?=\s+(?:Vertical\s+Segment|Processor\s+Number|Lithography|CPU\s+Specifications)|$)")
        set_if(specs, "arquitetura", codename)
    if "geracao" not in specs:
        generation = first_match(text, r"(?:Product\s+Collection\s*)?(\d{1,2})(?:st|nd|rd|th)\s+Generation\s+(?:Intel|AMD)") or first_match(text, r"(?:^|\n)\s*Generation\s*:?\s*(\d{1,2})", flags=re.I | re.M)
        set_if(specs, "geracao", generation)
    if "linha" not in specs:
        line = first_match(text, r"(?:Product\s+Collection\s*)?\d{1,2}(?:st|nd|rd|th)\s+Generation\s+(Intel\s+Core(?:\s+Ultra)?\s+[3579i]+)")
        set_if(specs, "linha", line)
    return specs


def extract_motherboard(mapping, text):
    specs = {}
    socket = attr(
        mapping,
        "CPU_SOCKET", "SOCKET", "Socket", "Soquete",
        "Soquete do Processador", "Socket do Processador",
    ) or first_match(text, r"(?:Socket|Soquete)(?:\s+do\s+Processador)?\s*:?[ \t]*(LGA\s*\d{3,4}|AM[345]|sTRX4|TR4|sWRX8|[A-Za-z]{1,4}\d{2,4})")
    if socket:
        socket = re.sub(r"\s+", "", clean_text(socket)).upper()
    set_if(specs, "socket", socket)

    chipset = attr(mapping, "CHIPSET", "Chipset") or first_match(text, r"Chipset\s*:\s*([A-Za-z]{0,12}\s*[A-Z]?[0-9]{3,4})\b")
    set_if(specs, "chipset", chipset)

    form_value = attr(
        mapping,
        "FORM_FACTOR", "MOTHERBOARD_FORM_FACTOR", "Formato",
        "Formato da Placa Mãe", "Formato da Placa-Mãe",
    ) or first_match(text, r"(?:Formato(?:\s+da\s+Placa[- ]M[aã]e)?|Form\s*Factor)\s*:\s*([^,;|\n]+)")
    set_if(specs, "formato", normalize_form_factor(form_value))
    set_if(specs, "revisao", attr(mapping, "REVISION", "Revisão"))
    set_if(specs, "biosInicial", attr(mapping, "INITIAL_BIOS", "BIOS inicial"))

    mem_details = attr(mapping, "Memória")
    mem = attr(
        mapping,
        "RAM_MEMORY_TYPE", "MEMORY_TYPE", "Tipo de memória RAM", "Tipo de Memória",
    ) or mem_details or first_match(text, r"(?:Mem[oó]ria|Memory)\s*:\s*([^.;\n]+)")
    if memory_types(mem):
        specs["tiposMemoriaSuportados"] = memory_types(mem)

    mem_context = " ".join(filter(None, [mem, mem_details, text]))
    if re.search(r"\bSO[-_ ]?DIMM\b", mem_context, re.I):
        specs["formatosMemoriaSuportados"] = ["SO_DIMM"]
    elif re.search(r"\b(?:U?DIMM)\b", mem_context, re.I):
        specs["formatosMemoriaSuportados"] = ["DIMM"]

    slots = integer(attr(mapping, "RAM_SLOTS_NUMBER", "MEMORY_SLOTS_NUMBER", "Quantidade de slots de memória"))
    slot_source = mem_details or mem or ""
    if slots is None:
        m = re.search(r"\b(\d+)\s*(?:slots?|x)\s*(?:DDR[345]\s*)?(?:U?DIMM|SO[-_ ]?DIMM)?\b", slot_source, re.I)
        if m:
            slots = int(m.group(1))
    if slots is None:
        slots = text_integer(text, r"\b(\d+)\s+slots?\s+(?:DDR[345]\s+)?(?:de\s+)?mem[oó]ria\b")
    if slots is None:
        slots = text_integer(text, r"\b(\d+)\s*[xX]\s*(?:DDR[345]\s*)?(?:U?DIMM|SO[-_ ]?DIMM)(?:\s+DDR[345])?\b")
    set_if(specs, "slotsMemoria", slots)

    max_memory = capacity_gb(attr(
        mapping,
        "MAX_RAM_MEMORY_CAPACITY", "MAX_MEMORY_CAPACITY", "Capacidade máxima de memória",
        "Memória da Placa Mãe", "Memória da Placa-Mãe",
    ))
    if max_memory is None:
        max_memory = text_capacity(text, r"(?:Suporte\s+m[aá]ximo\s+de|Mem[oó]ria\s+m[aá]xima|Capacidade\s+m[aá]xima(?:\s+de\s+mem[oó]ria)?)\s*:?[ \t]*([0-9.,]+\s*(?:GB|TB))")
    set_if(specs, "capacidadeMaximaMemoriaGb", max_memory)

    # Frequências explícitas, inclusive fichas com "até 7600MHz em OC".
    frequency_source = " ".join(filter(None, [mem_details, mem]))
    if frequency_source:
        oc_values = []
        oc_group = re.search(r"([0-9]{4,5}(?:\s+[0-9]{4,5})*)\s*\(OC\)", frequency_source, re.I)
        if oc_group:
            oc_values = [int(x) for x in re.findall(r"\b\d{4,5}\b", oc_group.group(1))]
        if not oc_values:
            oc_values = [int(x) for x in re.findall(r"\b(\d{4,5})\s*(?:MHz|MT/s)?\s*(?:em\s+)?(?:\(OC\)|OC)\b", frequency_source, re.I)]
        if not oc_values:
            m = re.search(r"(?:DDR[345]\s+)?(?:at[eé]\s+)?(\d{4,5})\s*MHz\s+em\s+OC", frequency_source, re.I)
            if m:
                oc_values = [int(m.group(1))]
        if oc_values:
            specs["frequenciasMemoriaOverclockMhz"] = unique(oc_values)

        jedec = re.search(r"([0-9]{4,5}(?:\s+[0-9]{4,5})*)\s*\(JEDEC\)", frequency_source, re.I)
        if jedec:
            vals = unique(int(x) for x in re.findall(r"\b\d{4,5}\b", jedec.group(1)))
            if vals:
                specs["frequenciasMemoriaJedecMhz"] = vals

    storage_text = attr(mapping, "Interface de Armazenamento", "Armazenar", "Armazenamento") or text or ""
    sata = integer(attr(mapping, "SATA_PORTS_NUMBER", "Quantidade de portas SATA"))
    if sata is None:
        m = re.search(r"\b(\d+)\s+(?:conectores?|portas?)\s+SATA\b|\b(\d+)\s*[xX]\s*SATA\b", storage_text, re.I)
        if m:
            sata = int(m.group(1) or m.group(2))
    set_if(specs, "portasSata", sata)

    m2 = integer(attr(mapping, "M2_SLOTS_NUMBER", "Quantidade de slots M.2", "Slots M.2"))
    if m2 is None:
        m = re.search(r"\b(\d+)\s+(?:conectores?|slots?)\s+M\.?(?:2)\b|\b(\d+)\s*[xX]\s*M\.?(?:2)\b", storage_text, re.I)
        if m:
            m2 = int(m.group(1) or m.group(2))
    set_if(specs, "slotsM2", m2)

    # Para a versão da placa, prioriza o slot principal explicitamente descrito.
    pcie = attr(mapping, "PCIE_VERSION", "PCI_EXPRESS_VERSION", "Versão PCIe")
    if not pcie:
        pcie = first_match(text, r"(?:slot\s+principal\s+)?PCI(?:e|[- ]?E)?\s*([345](?:\.0)?)\s*x?16")
    if not pcie:
        pcie = first_match(text, r"PCI(?:e|[- ]?E)?\s*([345](?:\.0)?)")
    set_if(specs, "versaoPcie", first_match(pcie or "", r"([345](?:[.,]0)?)") if pcie else None)

    ethernet = attr(mapping, "ETHERNET", "LAN", "Ethernet", "Rede")
    set_if(specs, "ethernet", ethernet)

    wifi = boolean(attr(mapping, "WITH_WIFI", "HAS_WIFI", "Wi-Fi"))
    if wifi is None and re.search(r"\bWi[- ]?Fi\s*(?:6E?|7)?\b", text or "", re.I):
        wifi = True
    set_if(specs, "wifi", wifi)
    bt = boolean(attr(mapping, "WITH_BLUETOOTH", "HAS_BLUETOOTH", "Bluetooth"))
    if bt is None and re.search(r"\bBluetooth\s*[45](?:\.\d)?\b", text or "", re.I):
        bt = True
    set_if(specs, "bluetooth", bt)

    if re.search(r"\bXMP\b", text or "", re.I):
        specs["suportaXmp"] = True
    if re.search(r"\bEXPO\b", text or "", re.I):
        specs["suportaExpo"] = True

    # "Suporte para módulos ECC e Non-ECC" significa que ECC é suportado.
    if re.search(r"\bsuporte\s+(?:para\s+)?(?:m[oó]dulos?\s+)?ECC\b|\bsuporta\s+ECC\b", text or "", re.I):
        specs["suportaEcc"] = True
    elif re.search(r"\b(?:apenas\s+)?non[- ]?ECC\b|\bmem[oó]ria\s+n[aã]o\s+ECC\b|\bn[aã]o\s+suporta\s+ECC\b", text or "", re.I):
        specs["suportaEcc"] = False

    if re.search(r"\b(?:sem\s+buffer|unbuffered)\b", text or "", re.I):
        specs["suportaMemoriaRegistrada"] = False
    if re.search(r"\bBIOS\s+Flashback\b|\bFlash\s+BIOS\b|\bQ[- ]Flash\s+Plus\b", text or "", re.I):
        specs["biosFlashback"] = True

    outputs = []
    for label, pattern in [
        ("HDMI", r"\bHDMI\b"),
        ("DisplayPort", r"\bDisplay\s*Port\b|\bDP\b"),
        ("DVI", r"\bDVI\b"),
        ("VGA", r"\bVGA\b"),
    ]:
        if re.search(pattern, text or "", re.I):
            outputs.append(label)
    if outputs:
        specs["saidasVideo"] = outputs
    return specs

def extract_ram(mapping, text):
    specs = {}
    source = attr(
        mapping,
        "RAM_MEMORY_TYPE", "MEMORY_TYPE", "Tipo de memória RAM", "Tipo de Memória",
    ) or text
    types = memory_types(source)
    if len(types) == 1:
        specs["tipo"] = types[0]

    token = normalize_key(attr(mapping, "RAM_FORM_FACTOR", "FORM_FACTOR", "Formato") or text)
    if "so_dimm" in token or "sodimm" in token:
        specs["formato"] = "SO_DIMM"
    elif re.search(r"\b(?:U?DIMM)\b", text or "", re.I):
        specs["formato"] = "DIMM"

    kit = re.search(r"\b(\d+)\s*[xX]\s*(\d+)\s*GB\b", text or "", re.I)
    if kit:
        specs["quantidadeModulos"] = int(kit.group(1))
        specs["capacidadePorModuloGb"] = int(kit.group(2))
    else:
        set_if(specs, "quantidadeModulos", integer(attr(mapping, "MODULES_NUMBER", "Quantidade de módulos")))
        # Não convertemos automaticamente a capacidade total do produto em
        # capacidade por módulo: um anúncio de 16 GB pode ser um kit 2x8 GB.
        set_if(specs, "capacidadePorModuloGb", capacity_gb(attr(mapping, "CAPACITY_PER_MODULE", "Capacidade por módulo")))

    freq = frequency_mhz(attr(
        mapping,
        "RAM_MEMORY_SPEED", "MEMORY_SPEED", "Frequência", "Velocidade da memória", "Velocidade de Clock",
    )) or text_frequency(text, r"\b([0-9]{3,5}\s*MHz)\b")
    set_if(specs, "frequenciaMhz", freq)
    set_if(specs, "frequenciaJedecMhz", frequency_mhz(attr(mapping, "JEDEC_FREQUENCY", "Frequência JEDEC")))
    set_if(specs, "latenciaCl", integer(attr(mapping, "CAS_LATENCY", "LATENCY", "Latência CAS", "Latência CL", "Latência")) or text_integer(text, r"\bCL\s*(\d{1,3})\b"))
    set_if(specs, "tensaoVolts", number(attr(mapping, "VOLTAGE", "Tensão", "Voltagem")) or text_number(text, r"(?:Tens[aã]o|Voltagem|Voltage)\s*:\s*([0-9.,]+)\s*V"))
    set_if(specs, "alturaMm", number(attr(mapping, "HEIGHT", "Altura")))
    ecc = boolean(attr(mapping, "ECC", "WITH_ECC", "ECC"))
    set_if(specs, "ecc", ecc)
    registered = boolean(attr(mapping, "REGISTERED", "Memória registrada"))
    set_if(specs, "registrada", registered)
    if re.search(r"\bXMP\b", text or "", re.I):
        specs["suportaXmp"] = True
    if re.search(r"\bEXPO\b", text or "", re.I):
        specs["suportaExpo"] = True
    if re.search(r"\b(?:RGB|ARGB)\b", text or "", re.I):
        specs["rgb"] = True
    return specs


def extract_gpu(mapping, text):
    specs = {}
    set_if(specs, "chipset", attr(mapping, "CHIPSET", "GPU_CHIPSET", "Chipset"))
    gpu = attr(mapping, "GPU_MODEL", "GRAPHICS_PROCESSOR", "GPU", "Modelo da GPU")

    # A ficha pode trazer só a família (ex.: "AMD Radeon RX série 9000")
    # enquanto o título informa o chip exato (ex.: "AMD Radeon RX 9070 XT").
    exact_gpu = (
        first_match(text, r"\b(AMD\s+Radeon\s+RX\s*\d{4}(?:\s*(?:XTX|XT|GRE))?)\b")
        or first_match(text, r"\b(NVIDIA\s+GeForce\s+(?:RTX|GTX)\s*\d{3,4}(?:\s*(?:Ti|SUPER))?)\b")
        or first_match(text, r"\b((?:RX|RTX|GTX)\s*\d{3,4}(?:\s*(?:XTX|XT|GRE|Ti|SUPER))?)\b")
    )
    generic_family = bool(gpu and re.search(r"\b(?:s[eé]rie|series)\b", str(gpu), re.I))
    if exact_gpu and (not gpu or generic_family):
        gpu = exact_gpu
    if not gpu:
        gpu = first_match(text, r"\b((?:AMD\s+Radeon|NVIDIA\s+GeForce)\s+(?:RX|RTX|GTX)?\s*\d{3,5}(?:\s*XT|\s*Ti|\s*SUPER)?)\b")
    set_if(specs, "gpu", gpu)

    arch = attr(mapping, "GPU_ARCHITECTURE", "ARCHITECTURE", "Arquitetura")
    if not arch:
        arch = (
            first_match(text, r"\b(?:arquitetura\s+)?AMD\s+(RDNA\s*\d)\b")
            or first_match(text, r"\b(RDNA\s*\d)\b")
            or first_match(text, r"\barquitetura\s+(?:NVIDIA\s+|AMD\s+)?([A-Za-z][A-Za-z0-9_-]{2,30})\b")
        )
    set_if(specs, "arquitetura", arch)

    vram = capacity_gb(attr(
        mapping,
        "VRAM", "VRAM_MEMORY_CAPACITY", "GRAPHICS_MEMORY_CAPACITY", "Memória de vídeo", "Memória de Vídeo", "Capacidade",
    ))
    if vram is None:
        vram = text_capacity(text, r"\b(\d+\s*GB)\s+(?:GDDR\d+|VRAM)\b")
    set_if(specs, "memoriaVideoGb", vram)

    memory_kind = attr(
        mapping,
        "VRAM_TYPE", "GRAPHICS_MEMORY_TYPE", "Tipo de memória de vídeo", "Tipo de Memória",
    ) or first_match(text, r"\b(GDDR[3567X]+)\b")
    set_if(specs, "tipoMemoriaVideo", memory_kind)
    set_if(specs, "barramentoBits", integer(attr(
        mapping,
        "MEMORY_BUS_WIDTH", "Barramento de memória", "Interface de Memória",
    )) or text_integer(text, r"(?:Barramento|Interface\s+de\s+Mem[oó]ria|Memory\s+Bus)\s*:\s*(\d+)\s*bits"))

    base = frequency_mhz(attr(mapping, "GPU_BASE_CLOCK", "BASE_CLOCK", "Clock base"))
    if base is None:
        base = text_frequency(text, r"(?:clock\s+base|Prim[aá]rias\s+clock\s+base)\s*(?:at[eé]|:)?\s*([0-9.,]+\s*MHz)")
    set_if(specs, "clockBaseMhz", base)
    boost = frequency_mhz(attr(mapping, "GPU_BOOST_CLOCK", "BOOST_CLOCK", "Clock boost", "Clock do Processador de Vídeo"))
    if boost is None:
        boost = text_frequency(text, r"(?:Clock\s+de\s+refor[cç]o|Clock\s+boost|Boost\s+Clock)\s*(?:(?:at[eé])\s*:?[ \t]*|:[ \t]*|)([0-9.,]+\s*MHz)")
    set_if(specs, "clockBoostMhz", boost)

    bus_text = attr(mapping, "Barramento", "Versão PCI Express", "PCIE_VERSION", "PCI_EXPRESS_VERSION") or text
    gen = first_match(bus_text or "", r"PCI(?:e|[- ]?E|\s+Express)?\s*([345](?:\.0)?)")
    set_if(specs, "geracaoPcie", integer(gen))
    width = first_match(bus_text or "", r"PCI(?:e|[- ]?E|\s+Express)?\s*[345](?:\.0)?\s*[xX]\s*(\d+)")
    set_if(specs, "larguraPcie", integer(width))

    # Dimensões da placa só entram quando a página rotula como cartão/placa.
    set_if(specs, "comprimentoMm", dimension_value_mm(attr(mapping, "LENGTH", "Comprimento")) or labeled_dimension_mm(text, "Comprimento"))
    set_if(specs, "alturaMm", dimension_value_mm(attr(mapping, "HEIGHT", "Altura")) or labeled_dimension_mm(text, "Altura"))
    set_if(specs, "espessuraMm", dimension_value_mm(attr(mapping, "THICKNESS", "Espessura")) or labeled_dimension_mm(text, "Espessura"))
    dim = attr(mapping, "Dimensões", "Dimensoes") or first_match(text, r"Dimens[oõ]es\s+do\s+cart[aã]o\s*:?[ \t]*([^|\n]+)")
    triplet = dimension_triplet_mm(dim)
    if triplet:
        # A captura XFX publica cm sem a unidade; números pequenos são cm.
        vals = list(triplet)
        if all(v < 100 for v in vals):
            vals = [round(v * 10, 3) for v in vals]
        if "comprimentoMm" not in specs:
            set_if(specs, "comprimentoMm", vals[0])
        if "alturaMm" not in specs:
            set_if(specs, "alturaMm", vals[1])
        if "espessuraMm" not in specs:
            set_if(specs, "espessuraMm", vals[2])

    slots = number(attr(mapping, "SLOTS", "Perfil do cartão", "Slots ocupados"))
    if slots is None:
        slots = text_number(text, r"Perfil\s+do\s+cart[aã]o\s*:?[ \t]*([0-9.,]+)\s*slots?")
    set_if(specs, "slotsOcupados", slots)

    consumo = integer(attr(mapping, "POWER_CONSUMPTION", "Consumo"))
    if consumo is None:
        consumo = text_integer(text, r"(?:TGP|TBP|Consumo)\s*:?\s*(\d{2,4})\s*W")
    set_if(specs, "consumoWatts", consumo)
    recommended = integer(attr(mapping, "RECOMMENDED_PSU_POWER", "Fonte recomendada"))
    if recommended is None:
        recommended = text_integer(text, r"(?:Requisito\s+m[ií]nimo\s+de\s+alimenta[cç][aã]o|Fonte\s+recomendada)\s*:?[ \t]*(\d{3,4})\s*watts?")
    set_if(specs, "potenciaFonteRecomendadaWatts", recommended)

    connectors = attr(mapping, "Conexões", "Conexoes", "Requisitos") or text
    pcie8 = first_match(connectors, r"(\d+)\s*[xX]\s*PCI[- ]?E\s*8\s*pinos?")
    if not pcie8:
        pcie8 = first_match(text, r"Alimenta[cç][aã]o\s+externa\s*(\d+)\s*[xX]\s*PCI[- ]?E\s*8\s*pinos?")
    set_if(specs, "conectoresPcie8Pinos", integer(pcie8))
    set_if(specs, "conectoresPcie6Pinos", integer(attr(mapping, "PCIE_6_PIN_CONNECTORS", "PCIe 6 pinos")))
    set_if(specs, "conectores12vhpwr", integer(attr(mapping, "12VHPWR_CONNECTORS", "12VHPWR")))
    set_if(specs, "conectores12v2x6", integer(attr(mapping, "12V_2X6_CONNECTORS", "12V-2x6")))

    outputs_text = attr(mapping, "Saídas", "Saidas") or text
    # Saídas: quantidade deve vir do rótulo da própria porta.
    # Algumas fichas do Magalu serializam duas colunas como:
    # "DisplayPort 2.1: 3 x HDMI | 2.1: 1x". Nesse caso o 3 pertence
    # ao DisplayPort e o 1 ao HDMI. Trate esse formato antes dos fallbacks.
    special_outputs = re.search(
        r"DisplayPort\s*(?:2\.1)?\s*:\s*(\d+)\s*[xX]\s*HDMI\s*(?:\|\s*)?(?:2\.1)?\s*:\s*(\d+)\s*[xX]",
        outputs_text or "", re.I,
    )
    if special_outputs:
        dp = special_outputs.group(1)
        hdmi = special_outputs.group(2)
    else:
        hdmi = (
            first_match(outputs_text, r"HDMI\s*(?:\|\s*)?(?:2\.1)?\s*:\s*(\d+)\s*[xX]")
            or first_match(outputs_text, r"(\d+)\s*(?:[xX]\s*)?HDMI\b")
        )
        dp = (
            first_match(outputs_text, r"DisplayPort\s*(?:2\.1)?\s*:\s*(\d+)\s*[xX]")
            or first_match(outputs_text, r"(\d+)\s*(?:[xX]\s*)?(?:Display\s*Port|DisplayPort|DP)\b")
        )
    set_if(specs, "hdmi", integer(hdmi))
    set_if(specs, "displayPort", integer(dp))
    outputs=[]
    if specs.get("hdmi"):
        outputs.append(f"{specs['hdmi']}x HDMI")
    if specs.get("displayPort"):
        outputs.append(f"{specs['displayPort']}x DisplayPort")
    if outputs:
        specs["saidasVideo"] = outputs
    return specs

def extract_storage(mapping, text):
    specs = {}
    product_type = attr(mapping, "STORAGE_TYPE", "TYPE", "Tipo") or text
    token = normalize_key(product_type)
    if "ssd" in token or "nvme" in token:
        specs["tipo"] = "SSD"
    elif "hdd" in token or "disco_rigido" in token:
        specs["tipo"] = "HDD"

    form = normalize_storage_format(attr(mapping, "FORM_FACTOR", "Formato", "Fator de forma") or text)
    set_if(specs, "formato", form)
    interface = normalize_storage_interface(attr(mapping, "INTERFACE", "STORAGE_INTERFACE", "Interface de Conexão", "Conectividade", "Interface") or text)
    set_if(specs, "interface", interface)

    cap = capacity_gb(attr(mapping, "STORAGE_CAPACITY", "Capacidade do Armazenamento", "Capacidade de Armazenamento", "CAPACITY", "Capacidade"))
    if cap is None:
        cap = text_capacity(text, r"\b([0-9.,]+\s*(?:GB|TB))\b")
    set_if(specs, "capacidadeGb", cap)

    m2code = first_match(text, r"\b22(30|42|60|80|110)\b")
    set_if(specs, "tamanhoM2Mm", int(m2code) if m2code else integer(attr(mapping, "M2_SIZE", "Tamanho M.2")))

    key = attr(mapping, "M2_KEY", "Chave M.2")
    if key:
        tk = normalize_key(key)
        if "b_m" in tk or "b_m_key" in tk:
            specs["chaveM2"] = "B_M"
        elif tk.startswith("m"):
            specs["chaveM2"] = "M"
        elif tk.startswith("b"):
            specs["chaveM2"] = "B"

    pcie = attr(mapping, "PCIE_VERSION", "PCI_EXPRESS_VERSION", "Geração PCIe") or first_match(text, r"PCIe?\s*(?:Gen\s*)?([345])(?:\.0)?")
    set_if(specs, "geracaoPcie", integer(pcie))
    lanes = integer(attr(mapping, "PCIE_LANES", "Pistas PCIe"))
    if lanes is None:
        m = re.search(r"PCIe?.{0,10}[xX](\d+)", text or "", re.I)
        lanes = int(m.group(1)) if m else None
    set_if(specs, "pistasPcie", lanes)

    details = attr(mapping, "Especificações", "Especificacoes", "Recursos") or text
    read = integer(attr(mapping, "SEQUENTIAL_READ_SPEED", "READ_SPEED", "Leitura sequencial"))
    write = integer(attr(mapping, "SEQUENTIAL_WRITE_SPEED", "WRITE_SPEED", "Escrita sequencial"))
    pair = re.search(
        r"Leitura\s*/\s*(?:escrita|grava[cç][aã]o)\s+sequencial\s*:\s*([0-9.,]+)\s*/\s*([0-9.,]+)\s*MB\s*/?\s*s",
        details or "", re.I,
    )
    if pair:
        read = read or grouped_integer(pair.group(1))
        write = write or grouped_integer(pair.group(2))
    if read is None:
        read = grouped_integer(first_match(text, r"(?:Leitura\s+sequencial|Leitura)\s*:?\s*(?:de\s+)?(?:at[eé]\s*)?([0-9.,]+)\s*MB\s*/?\s*s?"))
    if write is None:
        write = grouped_integer(first_match(text, r"(?:Escrita\s+sequencial|Grava[cç][aã]o(?:\s+sequencial)?|Write)\s*:?\s*(?:de\s+)?(?:at[eé]\s*)?([0-9.,]+)\s*MB\s*/?\s*s?"))
    set_if(specs, "leituraSequencialMbps", read)
    set_if(specs, "escritaSequencialMbps", write)

    # M.2 costuma publicar dimensões como 22 x 80 x 2,3 mm. Nesse contexto
    # a sequência representa largura x comprimento/profundidade x espessura.
    dim = attr(mapping, "Dimensão", "Dimensoes", "Dimensões", "Dimensões do Produto")
    triplet = dimension_triplet_mm(dim)
    if specs.get("formato") == "M2" and triplet:
        set_if(specs, "larguraMm", triplet[0])
        set_if(specs, "profundidadeMm", triplet[1])
        set_if(specs, "espessuraMm", triplet[2])

    heatsink = boolean(attr(mapping, "WITH_HEATSINK", "HEATSINK", "Possui dissipador"))
    if heatsink is None:
        heatsink = explicit_keyword_bool(text, [r"\bcom\s+dissipador\b", r"\bheatsink\b"], [r"\bsem\s+dissipador\b"])
    set_if(specs, "possuiDissipador", heatsink)
    return specs

def extract_psu(mapping, text):
    specs = {}
    set_if(specs, "formato", normalize_psu_format(
        attr(mapping, "FORM_FACTOR", "Formato", "Padrão de Conexão", "Padrão de Conexão da Fonte")
        or first_match(text, r"(?:Fator\s+de\s+forma|Formato|Form\s*Factor)\s*:?[ \t]*([^,;|\n]+)")
        or text
    ))
    watts = integer(attr(mapping, "POWER", "POWER_OUTPUT", "Potência")) or text_integer(text, r"\b(\d{3,4})\s*W\b")
    set_if(specs, "potenciaWatts", watts)
    cert = attr(mapping, "EFFICIENCY_CERTIFICATION", "CERTIFICATION", "Certificação", "Certificações") or first_match(text, r"\b(80\s*Plus\s*(?:White|Bronze|Silver|Gold|Platinum|Titanium)?)\b")
    set_if(specs, "certificacao", cert)

    details = attr(mapping, "Especificações", "Especificacoes") or text
    mod = attr(mapping, "MODULARITY", "Modularidade") or first_match(details, r"\bModular\s*:?\s*(N[aã]o|Sim|Semi[- ]?modular|Completamente|Totalmente)") or details
    token = normalize_key(mod)
    if token in {"nao", "no", "false"} or re.search(r"\b(?:modular\s*:?\s*n[aã]o|n[aã]o\s+modular|non[- ]modular)\b", str(mod), re.I):
        specs["modularidade"] = "NAO_MODULAR"
    elif "semi_modular" in token:
        specs["modularidade"] = "SEMI_MODULAR"
    elif token in {"sim", "yes", "true", "completamente", "totalmente"} or re.search(r"\b(?:full|completamente|totalmente)\s+modular\b", str(mod), re.I):
        specs["modularidade"] = "MODULAR"
    elif re.search(r"\bmodular\b", str(mod), re.I):
        specs["modularidade"] = "MODULAR"

    # Se a página não rotular a ordem, não inventamos P/L/A. Para fontes ATX,
    # a ficha de Kabum/Magalu usa 140x150x86 de forma consistente como P x L x A
    # quando o campo "Dimensões" está dentro das especificações da fonte.
    dim_source = attr(mapping, "Dimensões do Produto", "Dimensoes do Produto") or first_match(details, r"Dimens[oõ]es\s*:?\s*([^|]+)")
    dims = dimension_triplet_mm(dim_source)
    if dims:
        set_if(specs, "comprimentoMm", dims[0])
        set_if(specs, "larguraMm", dims[1])
        set_if(specs, "alturaMm", dims[2])

    set_if(specs, "padraoAtx", attr(mapping, "ATX_STANDARD", "Padrão ATX", "Padrão de Conexão da Fonte") or first_match(text, r"\bATX(?:12V)?\s*(3\.[01])\b"))
    if specs.get("padraoAtx"):
        m = re.search(r"(\d+(?:\.\d+)?)", str(specs["padraoAtx"]))
        if m:
            specs["padraoAtx"] = m.group(1)

    efficiency_raw = attr(mapping, "EFFICIENCY", "Eficiência")
    efficiency = number(efficiency_raw) if efficiency_raw and "%" in str(efficiency_raw) else None
    if efficiency is None:
        efficiency = number(first_match(details, r"(?:efici[eê]ncia)[^|%]{0,80}(\d{2,3}(?:[.,]\d+)?)\s*%"))
    set_if(specs, "eficienciaPercentual", efficiency)
    set_if(specs, "correnteLinha12vAmperes", number(attr(mapping, "12V_CURRENT", "Corrente linha 12V")))

    connectors = attr(mapping, "Conectores da Fonte", "Conectores") or details
    connector_patterns = {
        "conectoresAtx24Pinos": [r"(\d+)\s*[xX]\s*ATX\b", r"Conector\s+ATX\s*:\s*(\d+)", r"ATX\s*\(\s*24\s*pinos?\s*\)\s*(\d+)"],
        "conectoresEpsCpu": [r"(\d+)\s*[xX]\s*EPS\b", r"Conector\s+EPS\s*:\s*(\d+)", r"EPS\s*\(\s*8\s*pinos?\s*\)\s*(\d+)"],
        "conectoresPcie8Pinos": [r"(\d+)\s*[xX]\s*PCIe\b", r"Conector\s+PCIe\s*:\s*(\d+)", r"PCI[- ]?E\s*\(\s*6\s*\+\s*2\s*pinos?\s*\)\s*(\d+)"],
        "conectoresSata": [r"(\d+)\s*[xX]\s*SATA\b", r"Conector\s+SATA\s*:\s*(\d+)", r"SATA\s*\(\s*15\s*pinos?\s*\)\s*(\d+)"],
        "conectoresMolex": [r"(\d+)\s*[xX]\s*(?:PATA|MOLEX)\b", r"Conector\s+PATA\s*:\s*(\d+)", r"Conector\s+MOLEX\s*:\s*(\d+)", r"MOLEX\s*\(\s*4\s*pinos?\s*\)\s*(\d+)"],
    }
    for key, pats in connector_patterns.items():
        val = None
        for pat in pats:
            val = first_match(connectors, pat)
            if val:
                break
        set_if(specs, key, integer(val))

    # Alguns sellers escrevem o destino antes do conector, ex.:
    # "3x GPU / Placa de Vídeo (PCI-E 6+2 pinos)".
    if "conectoresAtx24Pinos" not in specs:
        set_if(specs, "conectoresAtx24Pinos", text_integer(connectors, r"(\d+)\s*[xX]\s*Placa[- ]m[aã]e\s+ATX"))
    if "conectoresEpsCpu" not in specs:
        cpu_counts = [int(v) for v in re.findall(r"(\d+)\s*[xX]\s*CPU\s*/\s*Processador\s*\((?:P4\+4|P8|EPS)[^)]*\)", connectors or "", re.I)]
        if cpu_counts:
            specs["conectoresEpsCpu"] = sum(cpu_counts)
    if "conectoresPcie8Pinos" not in specs:
        set_if(specs, "conectoresPcie8Pinos", text_integer(connectors, r"(\d+)\s*[xX]\s*GPU\s*/\s*Placa\s+de\s+V[ií]deo\s*\(PCI[- ]?E\s*6\+2\s*pinos?\)"))
    if "conectoresPcie6Pinos" not in specs:
        set_if(specs, "conectoresPcie6Pinos", text_integer(connectors, r"(\d+)\s*[xX]\s*GPU\s*/\s*Placa\s+de\s+V[ií]deo\s*\(PCI[- ]?E\s*6\s*pinos?\)"))
    if "conectoresSata" not in specs:
        set_if(specs, "conectoresSata", text_integer(connectors, r"(\d+)\s*[xX]\s*Armazenamento\s*/\s*HD\s*/\s*SSD\s*\(SATA\s*15\s*pinos?\)"))

    # 12V-2x6 é citado explicitamente na descrição da RM650e. Quantidade só é
    # definida quando singular/quantidade explícita aparece.
    count_12v2x6 = first_match(text, r"(?:\b(\d+)\s*[xX]\s*)?\b(?:cabo|conector)\s+(?:nativo\s+)?12V[- ]?2x6\b")
    if count_12v2x6:
        set_if(specs, "conectores12v2x6", integer(count_12v2x6) or 1)
    elif re.search(r"\bcabo\s+nativo\s+12V[- ]?2x6\b", text or "", re.I):
        specs["conectores12v2x6"] = 1

    set_if(specs, "conectoresPcie6Pinos", integer(attr(mapping, "PCIE_6_PIN_CONNECTORS", "PCIe 6 pinos")))
    set_if(specs, "conectores12vhpwr", integer(attr(mapping, "12VHPWR_CONNECTORS", "12VHPWR")))

    voltage = attr(mapping, "INPUT_VOLTAGE", "Tensão de entrada") or first_match(details, r"Faixa\s+de\s+tens[aã]o\s+de\s+entrada\s*:?\s*([^|]+)")
    set_if(specs, "tensaoEntrada", voltage)
    protections = [x for x in ["OVP", "OCP", "OPP", "OTP", "SCP", "UVP", "SIP"] if re.search(rf"\b{x}\b", details or "", re.I)]
    if protections:
        specs["protecoes"] = protections
    return specs

def extract_case(mapping, text):
    specs = {}
    set_if(specs, "tamanho", normalize_case_size(attr(mapping, "CASE_TYPE", "TOWER_TYPE", "Tamanho") or text))

    # Dimensões gerais só entram se a página as rotular explicitamente.
    set_if(specs, "alturaMm", dimension_value_mm(attr(mapping, "HEIGHT", "Altura")) or labeled_dimension_mm(text, r"(?:Dimens[oõ]es\s+do\s+Produto.{0,120})?Altura"))
    set_if(specs, "larguraMm", dimension_value_mm(attr(mapping, "WIDTH", "Largura")) or labeled_dimension_mm(text, r"(?:Dimens[oõ]es\s+do\s+Produto.{0,120})?Largura"))
    set_if(specs, "profundidadeMm", dimension_value_mm(attr(mapping, "DEPTH", "Profundidade")) or labeled_dimension_mm(text, r"(?:Dimens[oõ]es\s+do\s+Produto.{0,120})?Profundidade"))

    # Formato explícito L x W x H (Length/Width/Height) usado por alguns
    # anúncios: L 418mm x W 277mm x H 440mm.
    if not all(k in specs for k in ("alturaMm", "larguraMm", "profundidadeMm")):
        m = re.search(r"\bL\s*([0-9.,]+)\s*mm\s*[x×]\s*W\s*([0-9.,]+)\s*mm\s*[x×]\s*H\s*([0-9.,]+)\s*mm", text or "", re.I)
        if m:
            set_if(specs, "profundidadeMm", number(m.group(1)))
            set_if(specs, "larguraMm", number(m.group(2)))
            set_if(specs, "alturaMm", number(m.group(3)))

    board_scope = attr(mapping, "MOTHERBOARD_SUPPORT", "Placa mãe suportada", "Placa mae suportada")
    if not board_scope:
        board_scope = first_match(text, r"Placa[- ]?M[aã]e(?:\s+suportada)?\s*:\s*(.+?)(?=\s*\||\s+-\s+[A-ZÁÉÍÓÚ]|\s+Painel\s+Frontal|\s+Frontal\s+I/O|$)")
    boards = []
    if board_scope:
        for piece in re.split(r"[/,|;]+", board_scope):
            ff = normalize_form_factor(piece)
            if ff:
                boards.append(ff)
    if boards:
        specs["formatosPlacaMaeSuportados"] = unique(boards)

    psu_scope = attr(mapping, "PSU_FORM_FACTORS", "Formatos de fonte", "Tipo de Fonte") or first_match(text, r"(?:Tipo\s+de\s+Fonte|Fontes?\s+de\s+Alimenta[cç][aã]o)\s*:\s*([A-Za-z0-9_ -]+)")
    psus = []
    if psu_scope:
        for piece in re.split(r"[/,|;]+", psu_scope):
            ff = normalize_psu_format(piece)
            if ff:
                psus.append(ff)
    if psus:
        specs["formatosFonteSuportados"] = unique(psus)

    set_if(specs, "comprimentoMaximoGpuMm", number(attr(mapping, "MAX_GPU_LENGTH", "Comprimento máximo da GPU")) or text_number(text, r"Comprimento\s+M[aá]ximo\s+da\s+GPU\s*:?\s*([0-9.,]+)\s*mm") or text_number(text, r"placas?\s+de\s+v[ií]deo.{0,30}?at[eé]\s*([0-9.,]+)\s*mm"))
    set_if(specs, "alturaMaximaCoolerCpuMm", number(attr(mapping, "MAX_CPU_COOLER_HEIGHT", "Altura máxima do cooler")) or text_number(text, r"Altura\s+M[aá]xima\s+do\s+Cooler\s*:?\s*([0-9.,]+)\s*mm") or text_number(text, r"(?:Air\s+)?coolers?.{0,20}at[eé]\s*([0-9.,]+)\s*mm(?:\s+de\s+altura)?"))
    set_if(specs, "comprimentoMaximoFonteMm", number(attr(mapping, "MAX_PSU_LENGTH", "Comprimento máximo da fonte")))

    bay_text = attr(mapping, "Baias") or first_match(text, r"Baias\s*:\s*(.+?)(?=\s+-\s+Slots|\s+Slots\s+de\s+expans[aã]o|$)") or ""
    set_if(specs, "baias25", integer(first_match(bay_text, r"(\d+)\s*x?\s*(?:SSD\s*)?2[.,]5")))
    set_if(specs, "baias35", integer(first_match(bay_text, r"(\d+)\s*x?\s*(?:HDD\s*)?3[.,]5")))
    set_if(specs, "slotsTraseiros", integer(attr(mapping, "EXPANSION_SLOTS", "Slots traseiros", "Slots de expansão")) or text_integer(text, r"Slots\s+de\s+expans[aã]o\s*:\s*(\d+)"))

    vertical = boolean(attr(mapping, "VERTICAL_GPU_SUPPORT", "Suporta GPU vertical"))
    set_if(specs, "suportaGpuVertical", vertical)

    fans_scope = attr(mapping, "Ventoinhas Suportadas") or first_match(text, r"Ventoinhas\s+Suportadas\s*:\s*(.+?)(?=\s+-\s+Altura|\s+Altura\s+M[aá]xima|$)")
    if fans_scope:
        position_map = {
            "superior": "TOPO", "topo": "TOPO", "traseiro": "TRASEIRA", "traseira": "TRASEIRA",
            "inferior": "INFERIOR", "frente": "FRENTE", "frontal": "FRENTE", "lateral": "LATERAL",
        }
        supports = []
        for m in re.finditer(r"(Superior|Topo|Traseir[oa]|Inferior|Frente|Frontal|Lateral)\s*:\s*(\d+)\s*x\s*(\d+)\s*mm", fans_scope, re.I):
            supports.append({
                "posicao": position_map[m.group(1).casefold()],
                "tamanhoMm": int(m.group(3)),
                "quantidadeMaxima": int(m.group(2)),
            })
        if supports:
            specs["suportesFans"] = supports
    return specs

def extract_cooler(mapping, text):
    specs = {}
    source = " ".join(filter(None, [
        attr(mapping, "COOLER_TYPE", "Tipo"),
        attr(mapping, "Características", "Caracteristicas"),
        text,
    ]))
    token = normalize_key(source)
    if "water_cooler" in token or re.search(r"\bAIO\b", source, re.I):
        specs["tipo"] = "WATER_COOLER"
    elif "air_cooler" in token or re.search(r"\bair\s*cooler\b|\btower\s+cooler\b", source, re.I):
        specs["tipo"] = "AIR_COOLER"

    # Compatibilidade pode vir separada por plataforma ou agrupada em uma linha.
    compat_parts = [
        attr(mapping, "COMPATIBLE_SOCKETS", "CPU_SOCKETS", "Sockets suportados"),
        attr(mapping, "Compatibilidade"),
        attr(mapping, "Compatibilidade Intel"),
        attr(mapping, "Compatibilidade AMD"),
    ]
    compat_text = " | ".join(x for x in compat_parts if x) or text
    sockets = []
    for raw in re.findall(r"\b(?:AM[2345]|TR4|sTRX4|sTR5|LGA\s*(?:\d{3,4}|115X))\b", compat_text or "", re.I):
        sockets.append(re.sub(r"\s+", "", raw).upper())
    intel_group = first_match(compat_text, r"Intel\s*:\s*(.+?)(?=\s*(?:\||AMD\s*:|$))")
    # Em algumas fichas: Intel: LGA115X / 1200 / 1700 / 1366 ...
    if intel_group:
        for raw in re.findall(r"(?:LGA\s*)?(115X|\d{4})", intel_group, re.I):
            sockets.append("LGA" + raw.upper())
    if sockets:
        specs["socketsSuportados"] = unique(sockets)

    details = " | ".join(filter(None, [
        attr(mapping, "Especificações", "Especificacoes", "Especificações Técnicas", "Especificacoes Tecnicas"),
        attr(mapping, "Ventoinha"),
        text,
    ]))
    tdp = integer(attr(mapping, "TDP_SUPPORT", "THERMAL_CAPACITY", "Capacidade térmica", "TDP"))
    if tdp is None:
        tdp = text_integer(details, r"TDP\s*(?:M[aá]ximo)?\s*:?\s*(\d+)\s*W", r"(\d+)\s*W\s*TDP")
    set_if(specs, "capacidadeTermicaWatts", tdp)

    # Dimensões do corpo só são mapeadas quando eixos são rotulados; tripletos
    # genéricos ficam preservados em informacoesProdutoEncontradas.
    set_if(specs, "alturaMm", number(attr(mapping, "HEIGHT", "Altura")))
    set_if(specs, "larguraMm", number(attr(mapping, "WIDTH", "Largura")))
    set_if(specs, "profundidadeMm", number(attr(mapping, "DEPTH", "Profundidade")))

    rad = integer(attr(mapping, "RADIATOR_SIZE", "Tamanho do radiador"))
    if rad is None and specs.get("tipo") == "WATER_COOLER":
        rad = text_integer(text, r"Water\s+Cooler.{0,100}?\b(120|140|240|280|360|420)\s*mm\b", r"\bRadiador\s*(?:de\s*)?(120|140|240|280|360|420)\s*mm\b")
    set_if(specs, "tamanhoRadiadorMm", rad)

    qty = integer(attr(mapping, "FANS_NUMBER", "Quantidade de ventoinhas", "Número de Ventoinhas", "Numero de Ventoinhas"))
    if qty is None:
        qty = text_integer(details, r"N[uú]mero\s+de\s+Ventoinhas\s*:?\s*(\d+)")
    set_if(specs, "quantidadeVentoinhas", qty)

    fan_value = attr(mapping, "FAN_SIZE", "Tamanho da ventoinha")
    fan = integer(fan_value)
    fan_triplet = dimension_triplet_mm(fan_value or first_match(details, r"(?:Tamanho\s+da\s+Ventoinha|Ventoinha\s+Tamanho|Tamanho)\s*:\s*([0-9.,]+\s*(?:mm)?\s*[x×]\s*[0-9.,]+\s*(?:mm)?\s*[x×]\s*[0-9.,]+\s*mm)"))
    if fan_triplet:
        fan = int(round(fan_triplet[0]))
        set_if(specs, "espessuraVentoinhaMm", fan_triplet[2])
    if fan is None:
        fan = text_integer(details, r"(?:Ventoinha\s+(?:PWM\s+)?de|Tamanho\s*:?)[^0-9]{0,10}(80|92|120|140)\s*mm")
    set_if(specs, "tamanhoVentoinhaMm", fan)

    noise = number(attr(mapping, "NOISE_LEVEL", "Ruído", "Nível de Ruído"))
    if noise is None:
        noise = text_number(details, r"(?:N[ií]vel\s+de\s+Ru[ií]do|Ru[ií]do|Noise).{0,30}?([0-9.,]+)\s*dB")
    set_if(specs, "ruidoDb", noise)
    set_if(specs, "vidaUtilHoras", grouped_integer(attr(mapping, "LIFESPAN", "Vida útil")))
    set_if(specs, "pesoGramas", number(attr(mapping, "WEIGHT", "Peso")))

    speed = integer(attr(mapping, "MAX_FAN_SPEED", "MAX_RPM", "Velocidade máxima"))
    if speed is None:
        candidates = []
        for pat in [
            r"Velocidade\s+da\s+Ventoinha\s*:?\s*[0-9]+\s*[~\-]\s*([0-9]{3,5})",
            r"Velocidade\s*:?\s*([0-9]{3,5})\s*RPM",
            r"(?:Velocidade\s+m[aá]xima|Max\s+RPM).{0,20}?(\d{3,5})\s*RPM",
            r"at[eé]\s*(\d{3,5})\s*RPM",
        ]:
            for match in re.findall(pat, details or "", re.I):
                try:
                    candidates.append(int(match))
                except ValueError:
                    pass
        speed = max(candidates) if candidates else None
    set_if(specs, "velocidadeMaxRpm", speed)

    if re.search(r"\bARGB\b", details or "", re.I):
        specs["argb"] = True
        specs["rgb"] = True
    elif re.search(r"\bRGB\b", details or "", re.I):
        specs["rgb"] = True
    return specs

def extract_fan(mapping, text):
    specs = {}
    size = integer(attr(mapping, "FAN_SIZE", "SIZE", "Tamanho", "Dimensões do Produto")) or text_integer(text, r"\b(80|92|120|140|200)\s*mm\b")
    set_if(specs, "tamanhoMm", size)
    set_if(specs, "espessuraMm", number(attr(mapping, "THICKNESS", "Espessura")))

    min_rpm = integer(attr(mapping, "MIN_RPM", "RPM mínima"))
    max_rpm = integer(attr(mapping, "MAX_RPM", "RPM máxima"))
    if max_rpm is None:
        raw = first_match(text, r"(?:velocidades?\s+de\s+at[eé]|velocidade\s+m[aá]xima\s*:?[ \t]*|at[eé]\s+)([0-9][0-9.,]*)\s*RPM")
        if raw is None:
            raw = first_match(text, r"\b([0-9][0-9.,]*)\s*RPM\b")
        max_rpm = grouped_integer(raw)
    if min_rpm is None:
        raw = first_match(text, r"([0-9][0-9.,]*)\s*(?:-|~|a)\s*[0-9][0-9.,]*\s*RPM")
        min_rpm = grouped_integer(raw)
    set_if(specs, "rpmMinima", min_rpm)
    set_if(specs, "rpmMaxima", max_rpm)

    set_if(specs, "fluxoArCfm", number(attr(mapping, "AIRFLOW", "CFM", "Fluxo de ar")) or text_number(text, r"([0-9.,]+)\s*CFM"))
    set_if(specs, "pressaoEstaticaMmH2o", number(attr(mapping, "STATIC_PRESSURE", "Pressão estática")) or text_number(text, r"([0-9.,]+)\s*mm\s*H2O"))
    set_if(specs, "ruidoDb", number(attr(mapping, "NOISE_LEVEL", "Ruído", "Nível de Ruído")) or text_number(text, r"([0-9.,]+)\s*dB"))

    conn_source = attr(mapping, "CONNECTOR", "Conector")
    connector = connector_fan(conn_source or text)
    if connector is None and re.search(r"PWM\s+de\s+4\s+pinos?", text or "", re.I):
        connector = "PWM_4_PINOS"
    set_if(specs, "conector", connector)
    set_if(specs, "tensaoVolts", number(attr(mapping, "VOLTAGE", "Tensão")))
    set_if(specs, "correnteAmperes", number(attr(mapping, "CURRENT", "Corrente")))
    if connector == "PWM_4_PINOS" or re.search(r"\bPWM\b", text or "", re.I):
        specs["pwm"] = True
    if re.search(r"\bARGB\b", text or "", re.I):
        specs["argb"] = True
        specs["rgb"] = True
    elif re.search(r"\bRGB\b", text or "", re.I):
        specs["rgb"] = True
    reverse = explicit_keyword_bool(text, [r"fluxo\s+reverso", r"reverse\s+(?:blade|airflow)"], [])
    set_if(specs, "fluxoReverso", reverse)
    return specs

def extract_monitor(mapping, text):
    specs = {}
    set_if(specs, "tamanhoPolegadas", number(attr(mapping, "SCREEN_SIZE", "DISPLAY_SIZE", "Tamanho da tela", "Tamanho de tela")) or text_number(text, r"\b([0-9]{2}(?:[.,][0-9])?)\s*(?:\"|pol(?:egadas?)?)"))
    res = attr(mapping, "SCREEN_RESOLUTION", "RESOLUTION", "Resolução", "Resolução Máxima") or first_match(text, r"\b(\d{3,5}\s*[x×]\s*\d{3,5})\b")
    set_if(specs, "resolucao", resolution(res))
    set_if(specs, "taxaAtualizacaoHz", integer(attr(mapping, "REFRESH_RATE", "Taxa de atualização", "Taxa de Atualização da Tela")) or text_integer(text, r"\b(\d{2,4})\s*Hz\b"))
    # "Painel da Tela" é preferível a "Tipo de Display": MiniLED é tecnologia
    # de iluminação/display; HVA/IPS/VA/OLED descreve o painel no campo backend.
    panel = attr(mapping, "PANEL_TYPE", "Painel da Tela", "Tipo de painel")
    if not panel:
        panel = first_match(text, r"(?:Painel\s+da\s+Tela|Tipo\s+de\s+Painel)\s*:?\s*([A-Za-z0-9 -]+?)(?=\s+[A-ZÁÉÍÓÚ][a-záéíóú]+\s*:|\s+Formato\s+da\s+Tela|$)")
    if not panel:
        panel = first_match(text, r"\b(IPS|HVA|VA|TN|OLED|QD[- ]OLED)\b")
    set_if(specs, "tipoPainel", panel)
    set_if(specs, "tempoRespostaMs", number(attr(mapping, "RESPONSE_TIME", "Tempo de resposta")) or text_number(text, r"\b([0-9.,]+)\s*ms\b"))
    set_if(specs, "brilhoNits", integer(attr(mapping, "BRIGHTNESS", "Brilho")) or text_integer(text, r"\b(\d{2,4})\s*(?:nits?|cd/m)"))
    if re.search(r"\bHDR(?:10|400|600|1000)?\b", text or "", re.I):
        specs["hdr"] = True
    if re.search(r"Adaptive[- ]Sync", text or "", re.I):
        specs["adaptiveSync"] = True
    if re.search(r"G[- ]SYNC", text or "", re.I):
        specs["gSync"] = True
    if re.search(r"FreeSync", text or "", re.I):
        specs["freeSync"] = True
    connection_text = attr(mapping, "Conexões", "Conexoes") or text
    explicit_ports = {
        "hdmi": integer(attr(mapping, "HDMI", "Quantidade de HDMI")),
        "displayPort": integer(attr(mapping, "Display Port", "DisplayPort", "Quantidade de DisplayPort")),
        "usbC": integer(attr(mapping, "USB-C", "USB C", "Quantidade de USB-C")),
    }
    for key, pat in [("hdmi", r"HDMI"), ("displayPort", r"(?:DisplayPort|DP)"), ("usbC", r"USB[- ]?C")]:
        set_if(specs, key, explicit_ports.get(key) or ports_count(connection_text, pat))
    vesa = attr(mapping, "VESA_MOUNT", "VESA", "Padrão de Furação", "Padrao de Furacao") or first_match(text, r"(?:VESA|Padr[aã]o\s+de\s+Fura[cç][aã]o)\s*:?\s*(\d{2,3}\s*[x×]\s*\d{2,3})")
    if vesa:
        vesa = resolution(vesa).replace("×", "x") if resolution(vesa) else clean_text(vesa)
        vesa = re.sub(r"\s*mm\b", "", vesa, flags=re.I)
    set_if(specs, "vesa", vesa)
    return specs

def extract_mouse(mapping, text):
    specs = {}
    sensor = attr(mapping, "SENSOR_MODEL", "SENSOR", "Sensor")
    if not sensor:
        sensor = first_match(text, r"Sensor\s*:\s*([A-Za-z0-9 _.-]+?)(?=\s*DPI\s*:|\s*Polling\s+Rate\s*:|\n|$)")
    set_if(specs, "sensor", sensor)

    # Prefere a ficha técnica rotulada a números promocionais do título.
    dpi_raw = first_match(text, r"\bDPI\s*:\s*(?:At[eé]\s*)?([0-9][0-9.,]*)\s*DPI\b")
    dpi = grouped_integer(dpi_raw) if dpi_raw else integer(attr(mapping, "MAX_DPI", "DPI máximo"))
    if dpi is None:
        raw = first_match(text, r"(?:at[eé]\s*)?([0-9][0-9.,]*)\s*DPI\b")
        dpi = grouped_integer(raw)
    set_if(specs, "dpiMaximo", dpi)

    poll_raw = first_match(text, r"Polling\s+Rate\s*:\s*(?:At[eé]\s*)?([0-9][0-9.,]*)\s*Hz")
    polling = grouped_integer(poll_raw) if poll_raw else integer(attr(mapping, "POLLING_RATE", "Polling rate"))
    set_if(specs, "pollingRateHz", polling)

    buttons = integer(attr(mapping, "BUTTONS_NUMBER", "Quantidade de botões"))
    if buttons is None:
        buttons = text_integer(text, r"Bot[oõ]es\s+Program[aá]veis\s*:\s*(\d+)")
    set_if(specs, "botoes", buttons)

    weight = number(attr(mapping, "WEIGHT", "Peso", "Peso do Produto"))
    if weight is None:
        weight = text_number(text, r"(?:Peso|Weight)\s*:?\s*([0-9.,]+)\s*g")
    set_if(specs, "pesoGramas", weight)

    conn = attr(mapping, "CONNECTION_TYPE", "Conexão", "Conectividade", "Conexões")
    if not conn:
        conn = first_match(text, r"Conectividade\s*:\s*(USB\s*[0-9.]+|Bluetooth|Wireless|Sem\s+fio)")
    set_if(specs, "conexao", conn)
    source = normalize_key(conn or text)
    bt_flag = boolean(attr(mapping, "Com Bluetooth", "Bluetooth"))
    wireless_flag = boolean(attr(mapping, "É sem fio", "E sem fio", "Sem fio", "É sem fio USB", "E sem fio USB"))
    if "bluetooth" in source or bt_flag is True:
        specs["bluetooth"] = True
        specs["wireless"] = True
        if conn and "bluetooth" not in normalize_key(conn):
            specs["conexao"] = clean_text(f"Bluetooth / {conn}")
    if any(x in source for x in ["wireless", "sem_fio", "2_4_ghz", "2_4ghz"]) or wireless_flag is True:
        specs["wireless"] = True
    wired_flag = boolean(attr(mapping, "Com fio", "É com fio", "E com fio"))
    if wired_flag is True or re.search(r"\bcom\s+fio\b|\bwired\b|\bcabead[oa]\b", conn or "", re.I):
        specs["cabo"] = True
    elif wireless_flag is True or specs.get("wireless") is True or re.search(r"\bsem\s+fio\b", text or "", re.I):
        specs["cabo"] = False
    elif re.search(r"\bUSB\b", conn or "", re.I) and not re.search(r"receptor|receiver|dongle", conn or "", re.I):
        specs["cabo"] = True
    if re.search(r"\bdestros?\b|\bpara\s+destros?\b", text or "", re.I):
        specs["mao"] = "Destro"
    elif re.search(r"\bcanhotos?\b|\bpara\s+canhotos?\b", text or "", re.I):
        specs["mao"] = "Canhoto"
    elif re.search(r"\bambidestro\b", text or "", re.I):
        specs["mao"] = "Ambidestro"
    if re.search(r"\bRGB\b", text or "", re.I):
        specs["rgb"] = True
    return specs

def extract_keyboard(mapping, text):
    specs = {}
    set_if(specs, "switch", attr(mapping, "KEYBOARD_SWITCH", "Switch", "Tipo de switch"))
    set_if(specs, "layout", attr(mapping, "KEYBOARD_LAYOUT", "Layout", "Padrão de Teclado"))
    conn = attr(mapping, "CONNECTION_TYPE", "Tipo de conexão", "Conectividade") or first_match(text, r"(?:Conex[aã]o|Conectividade)\s*:\s*([^.;|\n]+)")
    set_if(specs, "conexao", conn)
    kind = attr(mapping, "KEYBOARD_TYPE", "Tipo", "Tipo de Teclado")
    kind_token = normalize_key(kind)
    size_from_kind = None
    if kind and any(x in kind_token for x in ["compacto", "compact", "full_size", "tkl", "tenkeyless"]):
        size_from_kind = kind
        kind = None
    if not kind:
        if re.search(r"\bmec[aâ]nico\b", text or "", re.I):
            kind = "Mecânico"
        elif re.search(r"\bmembrana\b", text or "", re.I):
            kind = "Membrana"
    set_if(specs, "tipo", kind)
    size = attr(mapping, "KEYBOARD_SIZE", "Tamanho") or size_from_kind or first_match(text, r"\b(TKL|100%|96%|80%|75%|65%|60%|Full[- ]size|Compacto)\b")
    set_if(specs, "tamanho", size)
    if re.search(r"\bABNT\s*2\b|\bABNT2\b", text or "", re.I):
        specs["abnt2"] = True

    usb_source = attr(mapping, "Conexões", "Conexoes") or conn or ""
    source = normalize_key(" ".join(filter(None, [conn, usb_source])))
    if "bluetooth" in source:
        specs["bluetooth"] = True
        specs["wireless"] = True
    if any(x in source for x in ["wireless", "sem_fio", "2_4"]):
        specs["wireless"] = True
    if "usb" in source:
        specs["usb"] = True
    if re.search(r"\bRGB\b|\bARGB\b", text or "", re.I):
        specs["rgb"] = True
    if re.search(r"hot[- ]?swap|hotswap|switch\s+remov[ií]vel", text or "", re.I):
        specs["hotSwap"] = True
    return specs

def extract_headset(mapping, text):
    specs = {}
    conn = attr(mapping, "CONNECTION_TYPE", "Tipo de conexão", "Conectividade", "Conexão", "Plugue de Alto-falante") or first_match(text, r"(?:Conex[aã]o|Conectividade)\s*:\s*([^.;|\n]+)")
    set_if(specs, "tipoConexao", conn)
    source = normalize_key(conn or text)
    if "bluetooth" in source:
        specs["bluetooth"] = True
        specs["wireless"] = True
    if any(x in source for x in ["wireless", "sem_fio", "2_4"]):
        specs["wireless"] = True

    driver = number(attr(mapping, "DRIVER_SIZE", "Driver"))
    if driver is None:
        raw_driver = first_match(text, r"drivers?[^.;|]{0,35}?\b([0-9.,]+)\s*mm") or first_match(text, r"(?:Driver|Falante)\s*:?\s*([0-9.,]+)\s*mm")
        driver = number(raw_driver)
    set_if(specs, "driverMm", driver)

    mic = boolean(attr(mapping, "WITH_MICROPHONE", "Microfone"))
    if mic is None and re.search(r"\bmicrofone\b", text or "", re.I):
        mic = True
    set_if(specs, "microfone", mic)
    if re.search(r"\b7\.1\b|\bsurround\b", text or "", re.I):
        specs["somSurround"] = True

    impedance_text = attr(mapping, "IMPEDANCE", "Impedância")
    impedance = None
    if impedance_text:
        # Quando há passiva e ativa, a passiva é a especificação do driver.
        raw = first_match(impedance_text, r"([0-9.,]+)\s*ohms?\s*\(passiva\)") or first_match(impedance_text, r"([0-9.,]+)\s*(?:ohms?|Ω)")
        impedance = grouped_integer(raw) if raw else None
    if impedance is None:
        impedance = text_number(text, r"([0-9.,]+)\s*(?:ohms?|Ω)")
    set_if(specs, "impedancia", impedance)

    weight_text = attr(mapping, "WEIGHT", "Peso", "Peso do Produto")
    weight = number(weight_text)
    if weight is not None and weight_text and re.search(r"\bkg\b", weight_text, re.I):
        weight *= 1000
    set_if(specs, "pesoGramas", weight)
    set_if(specs, "bateriaHoras", number(attr(mapping, "BATTERY_LIFE", "Autonomia da bateria")) or text_number(text, r"(?:Bateria|Autonomia)\s*:?\s*(?:at[eé]\s*)?([0-9.,]+)\s*h"))
    return specs

def extract_microphone(mapping, text):
    specs = {}
    details = attr(mapping, "Especificações", "Especificacoes") or text

    conn = attr(mapping, "CONNECTION_TYPE", "Conexão")
    if not conn:
        conn = first_match(details, r"Conex[aã]o\s+de\s+sa[ií]da\s*:\s*(.+?)(?=\s*\|\s*Consumo|\s*Consumo\s+de\s+energia|$)")
    if conn:
        # Mantém o texto técnico, mas remove observações parentéticas longas.
        compact = conn
        compact = re.sub(r"\s*\([^)]*(?:microfone|computador)[^)]*\)", "", compact, flags=re.I)
        compact = re.sub(r"\s+", " ", compact).strip()
        set_if(specs, "conexao", compact)

    polar = attr(mapping, "POLAR_PATTERN", "Padrão polar")
    if not polar:
        polar = first_match(details, r"Padr[aã]o\s+polar\s*:\s*([^|\n]+)")
    set_if(specs, "padraoPolar", polar)

    sample = number(attr(mapping, "SAMPLE_RATE", "Taxa de amostragem"))
    if sample is None:
        raw = first_match(details, r"taxa\s+de\s+amostragem\s*:\s*\d+\s*bits?/\s*([0-9.,]+)\s*k\s*[-–]\s*([0-9.,]+)\s*k\s*Hz")
        if raw:
            # first_match só retorna o grupo 1; usa regex completo para pegar o máximo.
            m = re.search(r"taxa\s+de\s+amostragem\s*:\s*\d+\s*bits?/\s*([0-9.,]+)\s*k\s*[-–]\s*([0-9.,]+)\s*k\s*Hz", details, re.I)
            if m:
                sample = max(number(m.group(1)) or 0, number(m.group(2)) or 0)
        if sample is None:
            m = re.search(r"taxa\s+de\s+amostragem[^|\n]*?([0-9.,]+)\s*kHz", details, re.I)
            sample = number(m.group(1)) if m else None
    set_if(specs, "taxaAmostragemKhz", sample)
    return specs

def extract_notebook(mapping, text):
    specs = {}
    cpu = attr(mapping, "PROCESSOR_MODEL", "CPU_MODEL", "Modelo do processador", "Processador") or first_match(text, r"(?:Processador|CPU)\s*:\s*([^.;|\n]+)")
    set_if(specs, "processadorNome", cpu)
    cpu_brand = attr(mapping, "PROCESSOR_BRAND", "Marca do processador")
    if not cpu_brand and cpu:
        cpu_brand = first_match(cpu, r"\b(Intel|AMD|Apple|Qualcomm)\b")
    set_if(specs, "processadorMarca", cpu_brand)
    set_if(specs, "processadorGeracao", attr(mapping, "PROCESSOR_GENERATION", "Geração do processador"))
    set_if(specs, "nucleos", integer(attr(mapping, "PROCESSOR_CORES_NUMBER", "Quantidade de núcleos", "Número de núcleos")))
    set_if(specs, "threads", integer(attr(mapping, "PROCESSOR_THREADS_NUMBER", "Quantidade de threads", "Número de threads")))
    set_if(specs, "clockBaseMhz", frequency_mhz(attr(mapping, "PROCESSOR_BASE_FREQUENCY", "Frequência base")))
    turbo = attr(mapping, "PROCESSOR_MAX_FREQUENCY", "Frequência máxima", "Velocidade do Processador")
    set_if(specs, "clockTurboMhz", frequency_mhz(turbo))

    gpu = attr(mapping, "GPU_MODEL", "GRAPHICS_CARD_MODEL", "Modelo da placa de vídeo", "GPU", "Placa de Vídeo")
    set_if(specs, "gpuNome", gpu)
    gpu_type = attr(mapping, "Tipo de Placa de Vídeo") or ""
    if re.search(r"\bintegrad[ao]\b", gpu_type, re.I) or re.search(r"\b(?:Intel\s+(?:Iris|UHD)|Radeon\s+Graphics|gr[aá]ficos\s+integrados)\b", gpu or text or "", re.I):
        specs["gpuIntegrada"] = True
    if re.search(r"\bdedicad[ao]\b", gpu_type, re.I) or re.search(r"\b(?:RTX|GTX|RX)\s*\d", gpu or "", re.I):
        specs["gpuDedicada"] = True
    elif re.search(r"\bintegrad[ao]\b", gpu_type, re.I):
        specs["gpuDedicada"] = False
    set_if(specs, "vramGb", capacity_gb(attr(mapping, "VRAM", "Memória de vídeo", "Memória da Placa de Vídeo")))

    ram = capacity_gb(attr(mapping, "RAM_MEMORY_CAPACITY", "RAM", "Memória RAM")) or text_capacity(text, r"\b(\d+\s*GB)\s+(?:de\s+)?RAM\b")
    set_if(specs, "ramInstaladaGb", ram)
    ram_type_source = attr(mapping, "RAM_MEMORY_TYPE", "Tipo de memória RAM", "Barramento da Memória") or ""
    types = memory_types(ram_type_source)
    if len(types) == 1:
        specs["tipoMemoria"] = types[0]
    set_if(specs, "frequenciaMhz", frequency_mhz(attr(mapping, "RAM_MEMORY_SPEED", "Frequência da memória", "Clock da Memória")))
    set_if(specs, "ramMaximaGb", capacity_gb(attr(mapping, "MAX_RAM_MEMORY_CAPACITY", "Memória RAM máxima", "Memória Expansível")))
    if specs.get("ramMaximaGb") and specs.get("ramInstaladaGb") and specs["ramMaximaGb"] > specs["ramInstaladaGb"]:
        specs["upgradeRam"] = True

    storage = capacity_gb(attr(mapping, "STORAGE_CAPACITY", "Capacidade de armazenamento", "Capacidade do Armazenamento")) or text_capacity(text, r"\b(\d+(?:[.,]\d+)?\s*(?:GB|TB))\s+(?:SSD|NVMe|HDD)\b")
    set_if(specs, "armazenamentoGb", storage)
    stype = attr(mapping, "STORAGE_TYPE", "Tipo de armazenamento") or first_match(text, r"\b(SSD\s+NVMe|SSD|HDD)\b")
    interface = attr(mapping, "Interface de Conexão")
    if stype and interface and "nvme" in normalize_key(interface) and "nvme" not in normalize_key(stype):
        stype = clean_text(f"{stype} NVMe")
    set_if(specs, "tipoArmazenamento", stype)

    set_if(specs, "tamanhoTelaPolegadas", number(attr(mapping, "SCREEN_SIZE", "Tamanho da tela")) or text_number(text, r"\b([0-9]{2}(?:[.,][0-9])?)\s*(?:\"|”|pol(?:egadas?)?)"))
    res = resolution(attr(mapping, "SCREEN_RESOLUTION", "Resolução da tela") or first_match(text, r"\b(\d{3,5}\s*[x×]\s*\d{3,5})\b"))
    if res and "x" in res:
        w, h = res.split("x")
        specs["resolucaoLargura"] = int(w)
        specs["resolucaoAltura"] = int(h)
    elif res:
        # Não inventa resolução numérica a partir de apenas "Full HD".
        pass
    set_if(specs, "taxaAtualizacaoHz", integer(attr(mapping, "REFRESH_RATE", "Taxa de atualização", "Taxa de Atualização da Tela")) or text_integer(text, r"\b(\d{2,4})\s*Hz\b"))
    set_if(specs, "tipoPainel", attr(mapping, "PANEL_TYPE", "Tipo de painel", "Painel da Tela") or first_match(text, r"\b(IPS|WVA|HVA|VA|TN|OLED|Mini[- ]LED)\b"))
    set_if(specs, "brilhoNits", integer(attr(mapping, "BRIGHTNESS", "Brilho")))
    set_if(specs, "bateriaWh", number(attr(mapping, "BATTERY_CAPACITY", "Capacidade da bateria")) or text_number(text, r"([0-9.,]+)\s*Wh\b"))
    set_if(specs, "autonomiaInformadaHoras", number(attr(mapping, "Duração Aproximada da Bateria", "Autonomia da bateria")) or text_number(text, r"(?:dura[cç][aã]o\s+aproximada\s+da\s+bateria|bateria\s+dura)\s*:?\s*(?:cerca\s+de\s*)?([0-9.,]+)\s*horas?"))

    weight = attr(mapping, "WEIGHT", "Peso", "Peso do Produto")
    if weight:
        n = number(weight)
        if n is not None:
            specs["pesoKg"] = round(n / 1000, 3) if re.search(r"\bg\b", weight, re.I) and not re.search(r"kg", weight, re.I) else n
    dims = attr(mapping, "Dimensões do Produto", "Dimensoes do Produto") or ""
    set_if(specs, "larguraMm", labeled_dimension_mm(dims, "Largura"))
    set_if(specs, "alturaMm", labeled_dimension_mm(dims, "Altura"))
    set_if(specs, "profundidadeMm", labeled_dimension_mm(dims, "Profundidade"))

    connectivity = attr(mapping, "Conectividade") or ""
    if re.search(r"Wi[- ]?Fi", connectivity, re.I):
        specs["wifi"] = clean_text(first_match(connectivity, r"(Wi[- ]?Fi(?:\s*\d(?:E)?)?)") or "Wi-Fi")
    if re.search(r"Bluetooth", connectivity, re.I):
        specs["bluetooth"] = clean_text(first_match(connectivity, r"(Bluetooth(?:\s*\d(?:\.\d+)?)?)") or "Bluetooth")

    connections = attr(mapping, "Conexões", "Conexoes") or ""
    usb_a = sum(int(x) for x in re.findall(r"(\d+)\s+(?:x\s*)?portas?\s+USB[^,;]*?Type[- ]?A", connections, re.I))
    usb_c = sum(int(x) for x in re.findall(r"(\d+)\s+(?:x\s*)?portas?\s+USB[^,;]*?Type[- ]?C", connections, re.I))
    if usb_c == 0 and re.search(r"\bPorta\s+USB\s+(?:Tipo|Type)[- ]?C\b", connections, re.I):
        usb_c = 1
    if usb_a:
        specs["usbA"] = usb_a
    if usb_c:
        specs["usbC"] = usb_c

    thunderbolt = ports_count(connections, r"Thunderbolt")
    if thunderbolt is None and re.search(r"\bThunderbolt(?:TM|™)?\s*4\b", connections, re.I):
        thunderbolt = 1
    set_if(specs, "thunderbolt", thunderbolt)

    # HDMI: nunca interpretar a versão (ex.: HDMI 2.1) como quantidade de portas.
    hdmi = None
    explicit_hdmi = re.findall(r"\b(\d+)\s*[xX]?\s*Portas?\s+HDMI\b", connections, re.I)
    if explicit_hdmi:
        hdmi = sum(int(v) for v in explicit_hdmi)
    elif re.search(r"\bPorta\s+HDMI(?:®)?(?:\s*\d(?:\.\d)?)?\b", connections, re.I):
        hdmi = 1
    set_if(specs, "hdmi", hdmi)
    set_if(specs, "displayPort", ports_count(connections, r"(?:DisplayPort|DP)"))
    ethernet = explicit_keyword_bool(connections, [r"\bEthernet\b", r"\bRJ[- ]?45\b", r"porta\s+para\s+cabo\s+de\s+rede"], [])
    set_if(specs, "ethernet", ethernet)
    leitor = explicit_keyword_bool(connections, [r"leitor\s+de\s+cart[aã]o", r"card\s+reader"], [])
    set_if(specs, "leitorCartao", leitor)

    set_if(specs, "sistemaOperacional", attr(mapping, "OPERATING_SYSTEM", "Sistema operacional"))
    multimedia = attr(mapping, "Multimídia", "Multimidia", "Funcionalidades") or text
    if re.search(r"\bwebcam\b|c[aâ]mera\s+(?:HD|FHD|Full\s*HD)", multimedia, re.I):
        specs["webcam"] = True
    webcam_res = first_match(multimedia, r"\b(\d{3,4}p)\b")
    if not webcam_res:
        webcam_res = first_match(multimedia, r"(?:webcam|c[aâ]mera)[^.;|]{0,60}?\b(FHD|Full\s*HD|HD)\b")
    set_if(specs, "resolucaoWebcam", webcam_res)
    keyboard = attr(mapping, "Padrão de Teclado", "Padrao de Teclado") or text
    if re.search(r"\bnum[eé]rico\b", keyboard, re.I):
        specs["tecladoNumerico"] = True
    if re.search(r"teclado\s+(?:retro)?iluminado|backlit\s+keyboard", text or "", re.I):
        specs["tecladoIluminado"] = True
    return specs

def extract_phone(mapping,text):
    specs={}
    set_if(specs,"processadorNome",attr(mapping,"PROCESSOR_MODEL","CHIPSET_MODEL","Processador"))
    set_if(specs,"ramGb",capacity_gb(attr(mapping,"RAM_MEMORY","RAM_MEMORY_CAPACITY","Memória RAM")))
    set_if(specs,"armazenamentoGb",capacity_gb(attr(mapping,"INTERNAL_MEMORY","STORAGE_CAPACITY","Memória interna")))
    set_if(specs,"tamanhoTelaPolegadas",number(attr(mapping,"SCREEN_SIZE","Tamanho da tela")))
    set_if(specs,"resolucao",resolution(attr(mapping,"SCREEN_RESOLUTION","Resolução da tela")))
    set_if(specs,"taxaAtualizacaoHz",integer(attr(mapping,"REFRESH_RATE","Taxa de atualização")))
    set_if(specs,"tipoTela",attr(mapping,"DISPLAY_TYPE","Tipo de tela"))
    set_if(specs,"cameraPrincipalMp",number(attr(mapping,"MAIN_CAMERA_RESOLUTION","Câmera principal")))
    set_if(specs,"cameraFrontalMp",number(attr(mapping,"FRONT_CAMERA_RESOLUTION","Câmera frontal")))
    set_if(specs,"bateriaMah",integer(attr(mapping,"BATTERY_CAPACITY","Capacidade da bateria")))
    set_if(specs,"carregamentoWatts",integer(attr(mapping,"FAST_CHARGING_POWER","Potência de carregamento")))
    if re.search(r"\b5G\b",text or "",re.I): specs["cincoG"]=True
    if re.search(r"\bNFC\b",text or "",re.I): specs["nfc"]=True
    set_if(specs,"sistemaOperacional",attr(mapping,"OPERATING_SYSTEM","Sistema operacional"))
    set_if(specs,"pesoGramas",number(attr(mapping,"WEIGHT","Peso")))
    set_if(specs,"cor",attr(mapping,"COLOR","Cor"))
    set_if(specs,"resistenciaAgua",attr(mapping,"IP_RATING","Resistência à água") or first_match(text,r"\b(IP\d{2})\b"))
    return specs



def extract_pc_montado(mapping,text):
    specs={}
    resolution_value = first_match(
        text,
        r"(?:resolu[cç][aã]o\s+recomendada|ideal\s+para|recomendado\s+para)\s*:?\s*(1080p|1440p|2160p|4K|Full\s*HD|QHD|UHD)",
    )
    set_if(specs,"resolucaoRecomendada",resolution_value)
    purpose = first_match(text, r"(?:Finalidade|Indicado\s+para|Ideal\s+para)\s*:\s*([^.;\n]+)")
    set_if(specs,"finalidade",purpose)

    component_patterns = [
        ("PROCESSADOR", r"(?:Processador|CPU)\s*:\s*([^;\n]+)"),
        ("PLACA_MAE", r"(?:Placa[- ]m[aã]e|Motherboard)\s*:\s*([^;\n]+)"),
        ("MEMORIA_RAM", r"(?:Mem[oó]ria\s+RAM|RAM)\s*:\s*([^;\n]+)"),
        ("PLACA_VIDEO", r"(?:Placa\s+de\s+v[ií]deo|GPU)\s*:\s*([^;\n]+)"),
        ("ARMAZENAMENTO", r"(?:Armazenamento|SSD|HDD)\s*:\s*([^;\n]+)"),
        ("FONTE", r"(?:Fonte|PSU)\s*:\s*([^;\n]+)"),
        ("GABINETE", r"Gabinete\s*:\s*([^;\n]+)"),
        ("COOLER", r"(?:Cooler|Water\s*Cooler|Air\s*Cooler)\s*:\s*([^;\n]+)"),
    ]
    components=[]
    for category,pattern in component_patterns:
        value=first_match(text,pattern)
        if value:
            components.append({"categoria":category,"nome":value,"quantidade":1})
    if components:
        specs["componentes"]=components
    return specs

def extract_generic(category,mapping,text):
    specs={}
    if category=="WEBCAM":
        set_if(specs,"resolucao",resolution(attr(mapping,"VIDEO_RESOLUTION","RESOLUTION","Resolução") or first_match(text,r"\b(\d{3,5}\s*[x×]\s*\d{3,5})\b")))
        set_if(specs,"fps",integer(attr(mapping,"FPS","FRAME_RATE","FPS")) or text_integer(text,r"\b(\d{2,3})\s*fps\b"))
        set_if(specs,"conexao",attr(mapping,"CONNECTION_TYPE","Conexão"))
        if re.search(r"\bmicrofone\b",text or "",re.I): specs["microfone"]=True
    elif category=="CONTROLE":
        conn=attr(mapping,"CONNECTION_TYPE","Conexão"); set_if(specs,"conexao",conn)
        source=normalize_key(conn or text)
        if "bluetooth" in source: specs["bluetooth"]=True; specs["wireless"]=True
        if any(x in source for x in ["wireless","sem_fio","2_4"]): specs["wireless"]=True
    elif category=="SUPORTE_MONITOR":
        set_if(specs,"quantidadeMonitores",integer(attr(mapping,"MONITORS_NUMBER","Quantidade de monitores")))
        set_if(specs,"vesa",attr(mapping,"VESA","VESA") or first_match(text,r"VESA\s*:?\s*(\d{2,3}\s*[x×]\s*\d{2,3})"))
        set_if(specs,"pesoMaximoKg",number(attr(mapping,"MAX_WEIGHT","Peso máximo")))
        set_if(specs,"tamanhoMaximoPolegadas",number(attr(mapping,"MAX_SCREEN_SIZE","Tamanho máximo")))
    elif category=="MOUSEPAD":
        set_if(specs,"larguraMm",number(attr(mapping,"WIDTH","Largura")))
        set_if(specs,"alturaMm",number(attr(mapping,"HEIGHT","Altura")))
        set_if(specs,"espessuraMm",number(attr(mapping,"THICKNESS","Espessura")))
        if re.search(r"\bRGB\b",text or "",re.I): specs["rgb"]=True
    elif category=="ILUMINACAO":
        set_if(specs,"tipo",attr(mapping,"TYPE","Tipo"))
        if re.search(r"\bARGB\b",text or "",re.I): specs["argb"]=True; specs["rgb"]=True
        elif re.search(r"\bRGB\b",text or "",re.I): specs["rgb"]=True
        set_if(specs,"conexao",attr(mapping,"CONNECTION_TYPE","Conexão"))
    elif category=="CADEIRA":
        set_if(specs,"material",attr(mapping,"MATERIAL","Material"))
        set_if(specs,"pesoMaximoKg",number(attr(mapping,"MAX_WEIGHT","Peso máximo")))
    elif category=="MESA":
        set_if(specs,"larguraCm",number(attr(mapping,"WIDTH","Largura")))
        set_if(specs,"profundidadeCm",number(attr(mapping,"DEPTH","Profundidade")))
        set_if(specs,"alturaCm",number(attr(mapping,"HEIGHT","Altura")))
        set_if(specs,"pesoMaximoKg",number(attr(mapping,"MAX_WEIGHT","Peso máximo")))
    return specs


def extract_specs(category: str | None, attributes, context_text=""):
    if not category:
        return {}
    mapping=attrs_map(attributes)
    text=context_text or ""
    extractors={
        "PROCESSADOR":extract_processor,
        "PLACA_MAE":extract_motherboard,
        "MEMORIA_RAM":extract_ram,
        "PLACA_VIDEO":extract_gpu,
        "ARMAZENAMENTO":extract_storage,
        "FONTE":extract_psu,
        "GABINETE":extract_case,
        "COOLER":extract_cooler,
        "VENTOINHA":extract_fan,
        "MONITOR":extract_monitor,
        "MOUSE":extract_mouse,
        "TECLADO":extract_keyboard,
        "FONE":extract_headset,
        "HEADSET":extract_headset,
        "MICROFONE":extract_microphone,
        "NOTEBOOK":extract_notebook,
        "CELULAR":extract_phone,
        "PC_MONTADO":extract_pc_montado,
    }
    fn=extractors.get(category)
    if fn:
        return fn(mapping,text)
    return extract_generic(category,mapping,text)
