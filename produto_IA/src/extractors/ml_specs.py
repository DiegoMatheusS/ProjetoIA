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
    token = normalize_key(value)
    if "nvme" in token or ("pcie" in token and "sata" not in token):
        return "NVME_PCIE"
    if "sas" in token:
        return "SAS"
    if "sata" in token:
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
    # Só conta quando a quantidade está explicitamente junto do conector.
    patterns = [
        rf"(\d+)\s*[xX]\s*{token_pattern}",
        rf"(?:quantidade\s+de\s+)?{token_pattern}\s*[:x-]?\s*(\d+)",
    ]
    for pattern in patterns:
        value = first_match(text, pattern)
        if value:
            return int(value)
    return None


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
    set_if(specs, "socket", (attr(mapping, "CPU_SOCKET", "PROCESSOR_SOCKET", "SOCKET", "Socket", "Soquete") or first_match(text, r"(?:Socket|Soquete)\s*:\s*([A-Za-z0-9+\-]+)")))
    if specs.get("socket"):
        specs["socket"] = re.sub(r"^(?:socket|soquete)\s*", "", specs["socket"], flags=re.I).upper()
    set_if(specs, "familia", attr(mapping, "PROCESSOR_FAMILY", "CPU_FAMILY", "Família do processador"))
    set_if(specs, "linha", attr(mapping, "LINE", "PROCESSOR_LINE", "Linha do processador"))
    set_if(specs, "geracao", attr(mapping, "PROCESSOR_GENERATION", "Geração do processador"))

    architecture = attr(mapping, "MICROARCHITECTURE", "PROCESSOR_MICROARCHITECTURE", "Microarquitetura", "Arquitetura")
    if architecture and normalize_key(architecture) not in {"x86_64", "x64", "amd64", "x86", "ia_32"}:
        specs["arquitetura"] = architecture

    set_if(specs, "litografiaNm", integer(attr(mapping, "LITHOGRAPHY", "PROCESSOR_LITHOGRAPHY", "Litografia", "Processo de fabricação")))
    set_if(specs, "nucleos", integer(attr(mapping, "PROCESSOR_CORES_NUMBER", "CPU_CORES_NUMBER", "CORES_NUMBER", "Quantidade de núcleos do processador", "Número de núcleos")))
    set_if(specs, "threads", integer(attr(mapping, "PROCESSOR_THREADS_NUMBER", "THREADS_NUMBER", "Quantidade de threads do processador", "Número de threads")))
    set_if(specs, "frequenciaBaseMhz", frequency_mhz(attr(mapping, "PROCESSOR_BASE_FREQUENCY", "BASE_CLOCK_FREQUENCY", "Frequência base", "Clock base")))
    set_if(specs, "frequenciaTurboMhz", frequency_mhz(attr(mapping, "MAX_TURBO_FREQUENCY", "PROCESSOR_MAX_FREQUENCY", "Frequência turbo máxima", "Frequência máxima")))
    set_if(specs, "cacheL2Mb", size_mb(attr(mapping, "L2_CACHE", "PROCESSOR_L2_CACHE", "Cache L2")))
    set_if(specs, "cacheL3Mb", size_mb(attr(mapping, "L3_CACHE", "PROCESSOR_L3_CACHE", "Cache L3")))
    set_if(specs, "tdpWatts", integer(attr(mapping, "THERMAL_DESIGN_POWER", "PROCESSOR_TDP", "TDP")))

    mem = attr(mapping, "RAM_MEMORY_TYPE", "SUPPORTED_RAM_MEMORY_TYPES", "Tipos de memória RAM suportados", "Tipo de memória RAM")
    if memory_types(mem):
        specs["tiposMemoriaSuportados"] = memory_types(mem)
    set_if(specs, "frequenciaMemoriaMaximaMhz", frequency_mhz(attr(mapping, "MAX_RAM_MEMORY_FREQUENCY", "MAX_MEMORY_FREQUENCY", "Frequência máxima da memória")))
    set_if(specs, "capacidadeMemoriaMaximaGb", capacity_gb(attr(mapping, "MAX_RAM_MEMORY_CAPACITY", "MAX_MEMORY_CAPACITY", "Capacidade máxima de memória")))
    set_if(specs, "canaisMemoria", integer(attr(mapping, "MEMORY_CHANNELS_NUMBER", "MEMORY_CHANNELS", "Canais de memória")))
    set_if(specs, "suportaEcc", boolean(attr(mapping, "ECC_SUPPORT", "WITH_ECC", "Suporta ECC")))
    set_if(specs, "temperaturaMaximaC", number(attr(mapping, "MAX_OPERATING_TEMPERATURE", "MAX_TEMPERATURE", "Temperatura máxima")))
    pcie = attr(mapping, "PCIE_VERSION", "PCI_EXPRESS_VERSION", "Versão PCI Express", "Versão PCIe")
    if pcie:
        set_if(specs, "versaoPcie", first_match(pcie, r"(\d+(?:[.,]\d+)?)") or pcie)
    set_if(specs, "lanesPcie", integer(attr(mapping, "PCIE_LANES_NUMBER", "PCI_EXPRESS_LANES_NUMBER", "Lanes PCIe")))
    set_if(specs, "coolerIncluso", boolean(attr(mapping, "COOLER_INCLUDED", "INCLUDES_CPU_COOLER", "Cooler incluso")))
    set_if(specs, "multiplicadorDesbloqueado", boolean(attr(mapping, "UNLOCKED_MULTIPLIER", "Multiplicador desbloqueado")))
    set_if(specs, "suporteOverclock", boolean(attr(mapping, "OVERCLOCK_SUPPORT", "Suporta overclock")))
    set_if(specs, "dataLancamento", attr(mapping, "RELEASE_DATE", "LAUNCH_DATE", "Data de lançamento"))

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
    return specs


def extract_motherboard(mapping, text):
    specs = {}
    socket = attr(mapping, "CPU_SOCKET", "SOCKET", "Socket", "Soquete") or first_match(text, r"(?:Socket|Soquete)\s*:\s*([A-Za-z0-9+\-]+)")
    set_if(specs, "socket", socket.upper() if socket else None)
    set_if(specs, "chipset", attr(mapping, "CHIPSET", "Chipset") or first_match(text, r"Chipset\s*:\s*([A-Za-z0-9+\-]+)"))
    form = normalize_form_factor(attr(mapping, "FORM_FACTOR", "MOTHERBOARD_FORM_FACTOR", "Formato") or first_match(text, r"(?:Formato|Form\s*Factor)\s*:\s*([^,;\n]+)"))
    set_if(specs, "formato", form)
    set_if(specs, "revisao", attr(mapping, "REVISION", "Revisão"))
    set_if(specs, "biosInicial", attr(mapping, "INITIAL_BIOS", "BIOS inicial"))
    mem = attr(mapping, "RAM_MEMORY_TYPE", "MEMORY_TYPE", "Tipo de memória RAM") or first_match(text, r"(?:Mem[oó]ria|Memory)\s*:\s*([^.;\n]+)")
    if memory_types(mem): specs["tiposMemoriaSuportados"] = memory_types(mem)
    specs["formatosMemoriaSuportados"] = ["DIMM"] if re.search(r"\bDIMM\b", text or "", re.I) else specs.get("formatosMemoriaSuportados", [])
    set_if(specs, "slotsMemoria", integer(attr(mapping, "RAM_SLOTS_NUMBER", "MEMORY_SLOTS_NUMBER", "Quantidade de slots de memória")) or text_integer(text, r"(\d+)\s*(?:x\s*)?(?:DIMM|slots?\s+de\s+mem[oó]ria)"))
    set_if(specs, "capacidadeMaximaMemoriaGb", capacity_gb(attr(mapping, "MAX_RAM_MEMORY_CAPACITY", "MAX_MEMORY_CAPACITY", "Capacidade máxima de memória")) or text_capacity(text, r"(?:Mem[oó]ria\s+m[aá]xima|Capacidade\s+m[aá]xima(?:\s+de\s+mem[oó]ria)?)\s*:\s*([0-9.,]+\s*(?:GB|TB))"))
    set_if(specs, "portasSata", integer(attr(mapping, "SATA_PORTS_NUMBER", "Quantidade de portas SATA")) or text_integer(text, r"(?:Portas?\s+SATA|SATA\s+ports?)\s*:\s*(\d+)"))
    pcie = attr(mapping, "PCIE_VERSION", "PCI_EXPRESS_VERSION", "Versão PCIe") or first_match(text, r"PCIe?\s*([345](?:\.0)?)")
    set_if(specs, "versaoPcie", first_match(pcie or "", r"([345](?:[.,]0)?)") if pcie else None)
    set_if(specs, "ethernet", attr(mapping, "ETHERNET", "LAN", "Ethernet"))
    wifi = boolean(attr(mapping, "WITH_WIFI", "HAS_WIFI", "Wi-Fi"))
    if wifi is None and re.search(r"\bWi[- ]?Fi\s*(?:6E?|7)?\b", text or "", re.I): wifi = True
    set_if(specs, "wifi", wifi)
    bt = boolean(attr(mapping, "WITH_BLUETOOTH", "HAS_BLUETOOTH", "Bluetooth"))
    if bt is None and re.search(r"\bBluetooth\s*[45](?:\.\d)?\b", text or "", re.I): bt = True
    set_if(specs, "bluetooth", bt)
    if re.search(r"\bXMP\b", text or "", re.I): specs["suportaXmp"] = True
    if re.search(r"\bEXPO\b", text or "", re.I): specs["suportaExpo"] = True
    if re.search(r"\bBIOS\s+Flashback\b|\bFlash\s+BIOS\b", text or "", re.I): specs["biosFlashback"] = True
    outputs = []
    for label, pattern in [("HDMI", r"\bHDMI\b"), ("DisplayPort", r"\bDisplayPort\b|\bDP\b"), ("DVI", r"\bDVI\b"), ("VGA", r"\bVGA\b")]:
        if re.search(pattern, text or "", re.I): outputs.append(label)
    if outputs: specs["saidasVideo"] = outputs
    return specs


def extract_ram(mapping, text):
    specs = {}
    source = attr(mapping, "RAM_MEMORY_TYPE", "MEMORY_TYPE", "Tipo de memória RAM") or text
    types = memory_types(source)
    if len(types) == 1: specs["tipo"] = types[0]
    token = normalize_key(attr(mapping, "RAM_FORM_FACTOR", "FORM_FACTOR", "Formato") or text)
    if "so_dimm" in token or "sodimm" in token: specs["formato"] = "SO_DIMM"
    elif re.search(r"\bDIMM\b", text or "", re.I): specs["formato"] = "DIMM"
    kit = re.search(r"\b(\d+)\s*[xX]\s*(\d+)\s*GB\b", text or "", re.I)
    if kit:
        specs["quantidadeModulos"] = int(kit.group(1)); specs["capacidadePorModuloGb"] = int(kit.group(2))
    else:
        set_if(specs, "quantidadeModulos", integer(attr(mapping, "MODULES_NUMBER", "Quantidade de módulos")))
        set_if(specs, "capacidadePorModuloGb", capacity_gb(attr(mapping, "CAPACITY_PER_MODULE", "Capacidade por módulo")))
    freq = frequency_mhz(attr(mapping, "RAM_MEMORY_SPEED", "MEMORY_SPEED", "Frequência", "Velocidade da memória")) or text_frequency(text, r"\b([0-9]{3,5}\s*MHz)\b")
    set_if(specs, "frequenciaMhz", freq)
    set_if(specs, "frequenciaJedecMhz", frequency_mhz(attr(mapping, "JEDEC_FREQUENCY", "Frequência JEDEC")))
    set_if(specs, "latenciaCl", integer(attr(mapping, "CAS_LATENCY", "LATENCY", "Latência CAS", "Latência CL")) or text_integer(text, r"\bCL\s*(\d{1,3})\b"))
    set_if(specs, "tensaoVolts", number(attr(mapping, "VOLTAGE", "Tensão")) or text_number(text, r"(?:Tens[aã]o|Voltage)\s*:\s*([0-9.,]+)\s*V"))
    set_if(specs, "alturaMm", number(attr(mapping, "HEIGHT", "Altura")))
    ecc = boolean(attr(mapping, "ECC", "WITH_ECC", "ECC")); set_if(specs, "ecc", ecc)
    registered = boolean(attr(mapping, "REGISTERED", "Memória registrada")); set_if(specs, "registrada", registered)
    if re.search(r"\bXMP\b", text or "", re.I): specs["suportaXmp"] = True
    if re.search(r"\bEXPO\b", text or "", re.I): specs["suportaExpo"] = True
    if re.search(r"\b(?:RGB|ARGB)\b", text or "", re.I): specs["rgb"] = True
    return specs


def extract_gpu(mapping, text):
    specs = {}
    set_if(specs, "chipset", attr(mapping, "CHIPSET", "GPU_CHIPSET", "Chipset"))
    set_if(specs, "gpu", attr(mapping, "GPU_MODEL", "GRAPHICS_PROCESSOR", "GPU", "Modelo da GPU"))
    arch = attr(mapping, "GPU_ARCHITECTURE", "ARCHITECTURE", "Arquitetura")
    if arch: specs["arquitetura"] = arch
    vram = capacity_gb(attr(mapping, "VRAM", "VRAM_MEMORY_CAPACITY", "GRAPHICS_MEMORY_CAPACITY", "Memória de vídeo"))
    if vram is None: vram = text_capacity(text, r"\b(\d+\s*GB)\s+(?:GDDR\d+|VRAM)\b")
    set_if(specs, "memoriaVideoGb", vram)
    memory_kind = attr(mapping, "VRAM_TYPE", "GRAPHICS_MEMORY_TYPE", "Tipo de memória de vídeo") or first_match(text, r"\b(GDDR[3567X]+)\b")
    set_if(specs, "tipoMemoriaVideo", memory_kind)
    set_if(specs, "barramentoBits", integer(attr(mapping, "MEMORY_BUS_WIDTH", "Barramento de memória")) or text_integer(text, r"(?:Barramento|Memory\s+Bus)\s*:\s*(\d+)\s*bits"))
    set_if(specs, "clockBaseMhz", frequency_mhz(attr(mapping, "GPU_BASE_CLOCK", "BASE_CLOCK", "Clock base")))
    set_if(specs, "clockBoostMhz", frequency_mhz(attr(mapping, "GPU_BOOST_CLOCK", "BOOST_CLOCK", "Clock boost")))
    pcie = attr(mapping, "PCIE_VERSION", "PCI_EXPRESS_VERSION", "Versão PCI Express") or first_match(text, r"PCIe?\s*([345](?:\.0)?)\s*[xX](\d+)")
    if pcie: set_if(specs, "geracaoPcie", integer(first_match(pcie, r"([345])") or pcie))
    width = integer(attr(mapping, "PCIE_LANES", "PCI_EXPRESS_LANES", "Largura PCIe"))
    if width is None:
        m = re.search(r"PCIe?\s*[345](?:\.0)?\s*[xX](\d+)", text or "", re.I)
        width = int(m.group(1)) if m else None
    set_if(specs, "larguraPcie", width)
    set_if(specs, "comprimentoMm", number(attr(mapping, "LENGTH", "BOARD_LENGTH", "Comprimento")) or text_number(text, r"(?:Comprimento|Length)\s*:\s*([0-9.,]+)\s*mm"))
    set_if(specs, "alturaMm", number(attr(mapping, "HEIGHT", "Altura")) or text_number(text, r"(?:Altura|Height)\s*:\s*([0-9.,]+)\s*mm"))
    set_if(specs, "espessuraMm", number(attr(mapping, "THICKNESS", "Espessura")) or text_number(text, r"(?:Espessura|Thickness)\s*:\s*([0-9.,]+)\s*mm"))
    set_if(specs, "slotsOcupados", number(attr(mapping, "SLOTS", "Slots ocupados")) or text_number(text, r"(?:Slots?\s+ocupados|Slot)\s*:\s*([0-9.,]+)"))
    set_if(specs, "consumoWatts", integer(attr(mapping, "TGP", "TBP", "POWER_CONSUMPTION", "Consumo")) or text_integer(text, r"(?:TGP|TBP|Consumo)\s*:\s*(\d+)\s*W"))
    set_if(specs, "potenciaFonteRecomendadaWatts", integer(attr(mapping, "RECOMMENDED_PSU_POWER", "Fonte recomendada")) or text_integer(text, r"(?:Fonte\s+recomendada|PSU\s+recomendad[ao])\s*:\s*(\d+)\s*W"))
    hdmi = ports_count(text, r"HDMI"); dp = ports_count(text, r"(?:DisplayPort|DP)")
    set_if(specs, "hdmi", hdmi); set_if(specs, "displayPort", dp)
    outputs=[]
    if re.search(r"\bHDMI\b", text or "", re.I): outputs.append("HDMI")
    if re.search(r"\bDisplayPort\b|\bDP\b", text or "", re.I): outputs.append("DisplayPort")
    if outputs: specs["saidasVideo"] = outputs
    return specs


def extract_storage(mapping, text):
    specs = {}
    product_type = attr(mapping, "STORAGE_TYPE", "TYPE", "Tipo") or text
    token = normalize_key(product_type)
    if "ssd" in token or "nvme" in token: specs["tipo"] = "SSD"
    elif "hdd" in token or "disco_rigido" in token: specs["tipo"] = "HDD"
    form = normalize_storage_format(attr(mapping, "FORM_FACTOR", "Formato") or text); set_if(specs, "formato", form)
    interface = normalize_storage_interface(attr(mapping, "INTERFACE", "STORAGE_INTERFACE", "Interface") or text); set_if(specs, "interface", interface)
    cap = capacity_gb(attr(mapping, "STORAGE_CAPACITY", "CAPACITY", "Capacidade"))
    if cap is None: cap = text_capacity(text, r"\b([0-9.,]+\s*(?:GB|TB))\b")
    set_if(specs, "capacidadeGb", cap)
    m2code = first_match(text, r"\b22(30|42|60|80|110)\b")
    set_if(specs, "tamanhoM2Mm", int(m2code) if m2code else integer(attr(mapping, "M2_SIZE", "Tamanho M.2")))
    key = attr(mapping, "M2_KEY", "Chave M.2")
    if key:
        tk=normalize_key(key)
        if "b_m" in tk or "b_m_key" in tk: specs["chaveM2"]="B_M"
        elif tk.startswith("m"): specs["chaveM2"]="M"
        elif tk.startswith("b"): specs["chaveM2"]="B"
    pcie = attr(mapping, "PCIE_VERSION", "PCI_EXPRESS_VERSION", "Geração PCIe") or first_match(text, r"PCIe?\s*(?:Gen\s*)?([345])(?:\.0)?")
    set_if(specs, "geracaoPcie", integer(pcie))
    lanes = integer(attr(mapping, "PCIE_LANES", "Pistas PCIe"))
    if lanes is None:
        m=re.search(r"PCIe?.{0,10}[xX](\d+)", text or "", re.I); lanes=int(m.group(1)) if m else None
    set_if(specs, "pistasPcie", lanes)
    set_if(specs, "leituraSequencialMbps", integer(attr(mapping, "SEQUENTIAL_READ_SPEED", "READ_SPEED", "Leitura sequencial")) or text_integer(text, r"(?:Leitura\s+sequencial|Read)\s*:?\s*(?:at[eé]\s*)?([0-9]+)\s*MB/s"))
    set_if(specs, "escritaSequencialMbps", integer(attr(mapping, "SEQUENTIAL_WRITE_SPEED", "WRITE_SPEED", "Escrita sequencial")) or text_integer(text, r"(?:Escrita\s+sequencial|Write)\s*:?\s*(?:at[eé]\s*)?([0-9]+)\s*MB/s"))
    heatsink = boolean(attr(mapping, "WITH_HEATSINK", "HEATSINK", "Possui dissipador"))
    if heatsink is None:
        heatsink = explicit_keyword_bool(text, [r"\bcom\s+dissipador\b", r"\bheatsink\b"], [r"\bsem\s+dissipador\b"])
    set_if(specs, "possuiDissipador", heatsink)
    return specs


def extract_psu(mapping, text):
    specs={}
    set_if(specs,"formato",normalize_psu_format(attr(mapping,"FORM_FACTOR","Formato") or first_match(text,r"(?:Formato|Form\s*Factor)\s*:\s*([^,;\n]+)") or text))
    watts=integer(attr(mapping,"POWER","POWER_OUTPUT","Potência")) or text_integer(text,r"\b(\d{3,4})\s*W\b")
    set_if(specs,"potenciaWatts",watts)
    cert=attr(mapping,"EFFICIENCY_CERTIFICATION","CERTIFICATION","Certificação") or first_match(text,r"\b(80\s*Plus\s*(?:White|Bronze|Silver|Gold|Platinum|Titanium)?)\b")
    set_if(specs,"certificacao",cert)
    mod=attr(mapping,"MODULARITY","Modularidade") or text
    token=normalize_key(mod)
    if "semi_modular" in token: specs["modularidade"]="SEMI_MODULAR"
    elif re.search(r"\b(?:full\s+)?modular\b", str(mod), re.I): specs["modularidade"]="MODULAR"
    elif re.search(r"\bnao\s+modular\b|\bnon[- ]modular\b", str(mod), re.I): specs["modularidade"]="NAO_MODULAR"
    set_if(specs,"comprimentoMm",number(attr(mapping,"LENGTH","Comprimento")))
    set_if(specs,"larguraMm",number(attr(mapping,"WIDTH","Largura")))
    set_if(specs,"alturaMm",number(attr(mapping,"HEIGHT","Altura")))
    set_if(specs,"padraoAtx",attr(mapping,"ATX_STANDARD","Padrão ATX") or first_match(text,r"\bATX\s*(3\.[01])\b"))
    set_if(specs,"eficienciaPercentual",number(attr(mapping,"EFFICIENCY","Eficiência")))
    set_if(specs,"correnteLinha12vAmperes",number(attr(mapping,"12V_CURRENT","Corrente linha 12V")))
    for key, aliases in {
        "conectoresAtx24Pinos":("ATX_24_PIN_CONNECTORS","ATX 24 pinos"),
        "conectoresEpsCpu":("EPS_CPU_CONNECTORS","EPS CPU"),
        "conectoresPcie6Pinos":("PCIE_6_PIN_CONNECTORS","PCIe 6 pinos"),
        "conectoresPcie8Pinos":("PCIE_8_PIN_CONNECTORS","PCIe 8 pinos"),
        "conectores12vhpwr":("12VHPWR_CONNECTORS","12VHPWR"),
        "conectores12v2x6":("12V_2X6_CONNECTORS","12V-2x6"),
        "conectoresSata":("SATA_CONNECTORS","Conectores SATA"),
        "conectoresMolex":("MOLEX_CONNECTORS","Molex"),
    }.items(): set_if(specs,key,integer(attr(mapping,*aliases)))
    set_if(specs,"tensaoEntrada",attr(mapping,"INPUT_VOLTAGE","Tensão de entrada"))
    protections=[x for x in ["OVP","OCP","OPP","OTP","SCP","UVP","SIP"] if re.search(rf"\b{x}\b",text or "",re.I)]
    if protections: specs["protecoes"]=protections
    return specs


def extract_case(mapping,text):
    specs={}
    set_if(specs,"tamanho",normalize_case_size(attr(mapping,"CASE_TYPE","TOWER_TYPE","Tamanho") or text))
    set_if(specs,"alturaMm",number(attr(mapping,"HEIGHT","Altura")) or text_number(text,r"Altura\s*:\s*([0-9.,]+)\s*mm"))
    set_if(specs,"larguraMm",number(attr(mapping,"WIDTH","Largura")) or text_number(text,r"Largura\s*:\s*([0-9.,]+)\s*mm"))
    set_if(specs,"profundidadeMm",number(attr(mapping,"DEPTH","Profundidade")) or text_number(text,r"Profundidade\s*:\s*([0-9.,]+)\s*mm"))
    boards=[]
    for value,label in [("E_ATX",r"\bE[- ]?ATX\b"),("MICRO_ATX",r"\bMicro[- ]?ATX\b|\bmATX\b"),("MINI_ITX",r"\bMini[- ]?ITX\b"),("ATX",r"(?<!E[- ])\bATX\b")]:
        if re.search(label,text or "",re.I): boards.append(value)
    if boards: specs["formatosPlacaMaeSuportados"]=unique(boards)
    psus=[]
    for value,pat in [("SFX_L",r"\bSFX[- ]?L\b"),("SFX",r"\bSFX\b"),("ATX",r"\bATX\b")]:
        if re.search(pat,attr(mapping,"PSU_FORM_FACTORS","Formatos de fonte") or "",re.I): psus.append(value)
    if psus: specs["formatosFonteSuportados"]=unique(psus)
    set_if(specs,"comprimentoMaximoGpuMm",number(attr(mapping,"MAX_GPU_LENGTH","Comprimento máximo da GPU")) or text_number(text,r"(?:GPU|placa\s+de\s+v[ií]deo).{0,30}m[aá]x(?:imo)?\s*:?\s*([0-9.,]+)\s*mm"))
    set_if(specs,"alturaMaximaCoolerCpuMm",number(attr(mapping,"MAX_CPU_COOLER_HEIGHT","Altura máxima do cooler")) or text_number(text,r"(?:Cooler\s+CPU).{0,30}m[aá]x(?:imo)?\s*:?\s*([0-9.,]+)\s*mm"))
    set_if(specs,"comprimentoMaximoFonteMm",number(attr(mapping,"MAX_PSU_LENGTH","Comprimento máximo da fonte")))
    set_if(specs,"baias25",integer(attr(mapping,"2_5_BAYS","Baias 2.5")))
    set_if(specs,"baias35",integer(attr(mapping,"3_5_BAYS","Baias 3.5")))
    set_if(specs,"slotsTraseiros",integer(attr(mapping,"EXPANSION_SLOTS","Slots traseiros")))
    vertical=boolean(attr(mapping,"VERTICAL_GPU_SUPPORT","Suporta GPU vertical")); set_if(specs,"suportaGpuVertical",vertical)
    return specs


def extract_cooler(mapping,text):
    specs={}
    token=normalize_key(attr(mapping,"COOLER_TYPE","Tipo") or text)
    if "water_cooler" in token or re.search(r"\bAIO\b",text or "",re.I): specs["tipo"]="WATER_COOLER"
    elif "air_cooler" in token or re.search(r"\bair\s*cooler\b|\btower\s+cooler\b",text or "",re.I): specs["tipo"]="AIR_COOLER"
    sockets=attr(mapping,"COMPATIBLE_SOCKETS","CPU_SOCKETS","Sockets suportados") or text
    found=re.findall(r"\b(?:AM[2345]|LGA\s*\d{3,4}|TR4|sTRX4|sTR5)\b",sockets or "",re.I)
    if found: specs["socketsSuportados"]=unique([re.sub(r"\s+","",x).upper() for x in found])
    set_if(specs,"capacidadeTermicaWatts",integer(attr(mapping,"TDP_SUPPORT","THERMAL_CAPACITY","Capacidade térmica")))
    set_if(specs,"alturaMm",number(attr(mapping,"HEIGHT","Altura")) or text_number(text,r"Altura\s*:\s*([0-9.,]+)\s*mm"))
    set_if(specs,"larguraMm",number(attr(mapping,"WIDTH","Largura")))
    set_if(specs,"profundidadeMm",number(attr(mapping,"DEPTH","Profundidade")))
    rad=integer(attr(mapping,"RADIATOR_SIZE","Tamanho do radiador")) or text_integer(text,r"\b(?:radiador|AIO)\s*(?:de\s*)?(120|140|240|280|360|420)\s*mm")
    set_if(specs,"tamanhoRadiadorMm",rad)
    set_if(specs,"quantidadeVentoinhas",integer(attr(mapping,"FANS_NUMBER","Quantidade de ventoinhas")))
    fan=integer(attr(mapping,"FAN_SIZE","Tamanho da ventoinha")) or text_integer(text,r"\b(80|92|120|140)\s*mm\s*(?:fan|ventoinha)")
    set_if(specs,"tamanhoVentoinhaMm",fan)
    set_if(specs,"ruidoDb",number(attr(mapping,"NOISE_LEVEL","Ruído")) or text_number(text,r"(?:Ru[ií]do|Noise).{0,20}([0-9.,]+)\s*dB"))
    set_if(specs,"vidaUtilHoras",integer(attr(mapping,"LIFESPAN","Vida útil")))
    set_if(specs,"pesoGramas",number(attr(mapping,"WEIGHT","Peso")))
    set_if(specs,"velocidadeMaxRpm",integer(attr(mapping,"MAX_FAN_SPEED","MAX_RPM","Velocidade máxima")) or text_integer(text,r"(?:Velocidade\s+m[aá]xima|Max\s+RPM).{0,20}(\d{3,5})\s*RPM"))
    if re.search(r"\bARGB\b",text or "",re.I): specs["argb"]=True; specs["rgb"]=True
    elif re.search(r"\bRGB\b",text or "",re.I): specs["rgb"]=True
    return specs


def extract_fan(mapping,text):
    specs={}
    size=integer(attr(mapping,"FAN_SIZE","SIZE","Tamanho")) or text_integer(text,r"\b(80|92|120|140|200)\s*mm\b")
    set_if(specs,"tamanhoMm",size)
    set_if(specs,"espessuraMm",number(attr(mapping,"THICKNESS","Espessura")))
    set_if(specs,"rpmMinima",integer(attr(mapping,"MIN_RPM","RPM mínima")))
    set_if(specs,"rpmMaxima",integer(attr(mapping,"MAX_RPM","RPM máxima")) or text_integer(text,r"(?:at[eé]\s*)?(\d{3,5})\s*RPM"))
    set_if(specs,"fluxoArCfm",number(attr(mapping,"AIRFLOW","CFM","Fluxo de ar")) or text_number(text,r"([0-9.,]+)\s*CFM"))
    set_if(specs,"pressaoEstaticaMmH2o",number(attr(mapping,"STATIC_PRESSURE","Pressão estática")) or text_number(text,r"([0-9.,]+)\s*mmH2O"))
    set_if(specs,"ruidoDb",number(attr(mapping,"NOISE_LEVEL","Ruído")) or text_number(text,r"([0-9.,]+)\s*dB"))
    connector=connector_fan(attr(mapping,"CONNECTOR","Conector") or text); set_if(specs,"conector",connector)
    set_if(specs,"tensaoVolts",number(attr(mapping,"VOLTAGE","Tensão")))
    set_if(specs,"correnteAmperes",number(attr(mapping,"CURRENT","Corrente")))
    if connector=="PWM_4_PINOS" or re.search(r"\bPWM\b",text or "",re.I): specs["pwm"]=True
    if re.search(r"\bARGB\b",text or "",re.I): specs["argb"]=True; specs["rgb"]=True
    elif re.search(r"\bRGB\b",text or "",re.I): specs["rgb"]=True
    reverse=explicit_keyword_bool(text,[r"fluxo\s+reverso",r"reverse\s+(?:blade|airflow)"],[]); set_if(specs,"fluxoReverso",reverse)
    return specs


def extract_monitor(mapping,text):
    specs={}
    set_if(specs,"tamanhoPolegadas",number(attr(mapping,"SCREEN_SIZE","DISPLAY_SIZE","Tamanho da tela")) or text_number(text,r"\b([0-9]{2}(?:[.,][0-9])?)\s*(?:\"|pol(?:egadas?)?)"))
    res=attr(mapping,"SCREEN_RESOLUTION","RESOLUTION","Resolução") or first_match(text,r"\b(\d{3,5}\s*[x×]\s*\d{3,5})\b"); set_if(specs,"resolucao",resolution(res))
    set_if(specs,"taxaAtualizacaoHz",integer(attr(mapping,"REFRESH_RATE","Taxa de atualização")) or text_integer(text,r"\b(\d{2,4})\s*Hz\b"))
    panel=attr(mapping,"PANEL_TYPE","DISPLAY_TYPE","Tipo de painel") or first_match(text,r"\b(IPS|VA|TN|OLED|QD[- ]OLED|Mini[- ]LED)\b"); set_if(specs,"tipoPainel",panel)
    set_if(specs,"tempoRespostaMs",number(attr(mapping,"RESPONSE_TIME","Tempo de resposta")) or text_number(text,r"\b([0-9.,]+)\s*ms\b"))
    set_if(specs,"brilhoNits",integer(attr(mapping,"BRIGHTNESS","Brilho")) or text_integer(text,r"\b(\d{2,4})\s*(?:nits?|cd/m)"))
    if re.search(r"\bHDR(?:10|400|600|1000)?\b",text or "",re.I): specs["hdr"]=True
    if re.search(r"Adaptive[- ]Sync",text or "",re.I): specs["adaptiveSync"]=True
    if re.search(r"G[- ]Sync",text or "",re.I): specs["gSync"]=True
    if re.search(r"FreeSync",text or "",re.I): specs["freeSync"]=True
    for key,pat in [("hdmi",r"HDMI"),("displayPort",r"(?:DisplayPort|DP)"),("usbC",r"USB[- ]?C")]: set_if(specs,key,ports_count(text,pat))
    set_if(specs,"vesa",attr(mapping,"VESA_MOUNT","VESA") or first_match(text,r"VESA\s*:?\s*(\d{2,3}\s*[x×]\s*\d{2,3})"))
    return specs


def extract_mouse(mapping,text):
    specs={}
    set_if(specs,"sensor",attr(mapping,"SENSOR_MODEL","SENSOR","Sensor"))
    set_if(specs,"dpiMaximo",integer(attr(mapping,"MAX_DPI","DPI máximo")) or text_integer(text,r"(?:at[eé]\s*)?([0-9]{3,6})\s*DPI"))
    set_if(specs,"pollingRateHz",integer(attr(mapping,"POLLING_RATE","Polling rate")) or text_integer(text,r"([0-9]{3,4})\s*Hz\s*(?:polling|taxa)"))
    set_if(specs,"botoes",integer(attr(mapping,"BUTTONS_NUMBER","Quantidade de botões")))
    set_if(specs,"pesoGramas",number(attr(mapping,"WEIGHT","Peso")) or text_number(text,r"(?:Peso|Weight)\s*:?\s*([0-9.,]+)\s*g"))
    conn=attr(mapping,"CONNECTION_TYPE","Conexão","Conectividade") or first_match(text,r"(?:Conex[aã]o|Conectividade)\s*:\s*([^.;\n]+)"); set_if(specs,"conexao",conn)
    source=normalize_key(conn or text)
    if "bluetooth" in source: specs["bluetooth"]=True; specs["wireless"]=True
    if any(x in source for x in ["wireless","sem_fio","2_4_ghz","2_4ghz"]): specs["wireless"]=True
    if re.search(r"\bUSB\b|\bcom\s+fio\b|\bwired\b",conn or "",re.I): specs["cabo"]=True
    if re.search(r"\bRGB\b",text or "",re.I): specs["rgb"]=True
    return specs


def extract_keyboard(mapping,text):
    specs={}
    set_if(specs,"switch",attr(mapping,"KEYBOARD_SWITCH","Switch","Tipo de switch"))
    set_if(specs,"layout",attr(mapping,"KEYBOARD_LAYOUT","Layout"))
    conn=attr(mapping,"CONNECTION_TYPE","Tipo de conexão","Conectividade") or first_match(text,r"(?:Conex[aã]o|Conectividade)\s*:\s*([^.;\n]+)"); set_if(specs,"conexao",conn)
    kind=attr(mapping,"KEYBOARD_TYPE","Tipo")
    if not kind:
        if re.search(r"\bmec[aâ]nico\b",text or "",re.I): kind="Mecânico"
        elif re.search(r"\bmembrana\b",text or "",re.I): kind="Membrana"
    set_if(specs,"tipo",kind)
    size=attr(mapping,"KEYBOARD_SIZE","Tamanho") or first_match(text,r"\b(100%|96%|80%|75%|65%|60%|TKL|Full[- ]size)\b"); set_if(specs,"tamanho",size)
    if re.search(r"\bABNT\s*2\b|\bABNT2\b",text or "",re.I): specs["abnt2"]=True
    source=normalize_key(conn or text)
    specs.update({k:True for k,cond in {
        "bluetooth":"bluetooth" in source,
        "wireless":any(x in source for x in ["wireless","sem_fio","2_4"]),
        "usb":"usb" in source,
        "rgb":bool(re.search(r"\bRGB\b|\bARGB\b",text or "",re.I)),
        "hotSwap":bool(re.search(r"hot[- ]?swap|hotswap",text or "",re.I)),
    }.items() if cond})
    return specs


def extract_headset(mapping,text):
    specs={}
    conn=attr(mapping,"CONNECTION_TYPE","Tipo de conexão","Conectividade") or first_match(text,r"(?:Conex[aã]o|Conectividade)\s*:\s*([^.;\n]+)"); set_if(specs,"tipoConexao",conn)
    source=normalize_key(conn or text)
    if "bluetooth" in source: specs["bluetooth"]=True; specs["wireless"]=True
    if any(x in source for x in ["wireless","sem_fio","2_4"]): specs["wireless"]=True
    set_if(specs,"driverMm",number(attr(mapping,"DRIVER_SIZE","Driver")) or text_number(text,r"(?:Driver|Falante)\s*:?\s*([0-9.,]+)\s*mm"))
    mic=boolean(attr(mapping,"WITH_MICROPHONE","Microfone"));
    if mic is None and re.search(r"\bmicrofone\b",text or "",re.I): mic=True
    set_if(specs,"microfone",mic)
    if re.search(r"\b7\.1\b|\bsurround\b",text or "",re.I): specs["somSurround"]=True
    set_if(specs,"impedancia",number(attr(mapping,"IMPEDANCE","Impedância")) or text_number(text,r"([0-9.,]+)\s*(?:ohms?|Ω)"))
    set_if(specs,"pesoGramas",number(attr(mapping,"WEIGHT","Peso")) or text_number(text,r"(?:Peso|Weight)\s*:?\s*([0-9.,]+)\s*g"))
    set_if(specs,"bateriaHoras",number(attr(mapping,"BATTERY_LIFE","Autonomia da bateria")) or text_number(text,r"(?:Bateria|Autonomia)\s*:?\s*(?:at[eé]\s*)?([0-9.,]+)\s*h"))
    return specs


def extract_microphone(mapping,text):
    specs={}
    set_if(specs,"conexao",attr(mapping,"CONNECTION_TYPE","Conexão") or first_match(text,r"(?:Conex[aã]o|Interface)\s*:\s*([^.;\n]+)"))
    set_if(specs,"padraoPolar",attr(mapping,"POLAR_PATTERN","Padrão polar") or first_match(text,r"(?:Padr[aã]o\s+polar)\s*:\s*([^.;\n]+)"))
    set_if(specs,"taxaAmostragemKhz",number(attr(mapping,"SAMPLE_RATE","Taxa de amostragem")) or text_number(text,r"([0-9.,]+)\s*kHz"))
    return specs


def extract_notebook(mapping,text):
    specs={}
    set_if(specs,"processadorNome",attr(mapping,"PROCESSOR_MODEL","CPU_MODEL","Modelo do processador","Processador") or first_match(text,r"(?:Processador|CPU)\s*:\s*([^.;\n]+)"))
    set_if(specs,"processadorMarca",attr(mapping,"PROCESSOR_BRAND","Marca do processador"))
    set_if(specs,"processadorGeracao",attr(mapping,"PROCESSOR_GENERATION","Geração do processador"))
    set_if(specs,"nucleos",integer(attr(mapping,"PROCESSOR_CORES_NUMBER","Quantidade de núcleos")))
    set_if(specs,"threads",integer(attr(mapping,"PROCESSOR_THREADS_NUMBER","Quantidade de threads")))
    set_if(specs,"clockBaseMhz",frequency_mhz(attr(mapping,"PROCESSOR_BASE_FREQUENCY","Frequência base")))
    set_if(specs,"clockTurboMhz",frequency_mhz(attr(mapping,"PROCESSOR_MAX_FREQUENCY","Frequência máxima")))
    set_if(specs,"gpuNome",attr(mapping,"GPU_MODEL","GRAPHICS_CARD_MODEL","Modelo da placa de vídeo","GPU"))
    if re.search(r"\b(?:RTX|GTX|RX)\s*\d",text or "",re.I): specs["gpuDedicada"]=True
    if re.search(r"\b(?:Intel\s+(?:Iris|UHD)|Radeon\s+Graphics|gr[aá]ficos\s+integrados)\b",text or "",re.I): specs["gpuIntegrada"]=True
    set_if(specs,"vramGb",capacity_gb(attr(mapping,"VRAM","Memória de vídeo")))
    ram=capacity_gb(attr(mapping,"RAM_MEMORY_CAPACITY","RAM","Memória RAM")) or text_capacity(text,r"\b(\d+\s*GB)\s+(?:de\s+)?RAM\b"); set_if(specs,"ramInstaladaGb",ram)
    types=memory_types(attr(mapping,"RAM_MEMORY_TYPE","Tipo de memória RAM") or text)
    if len(types)==1: specs["tipoMemoria"]=types[0]
    set_if(specs,"frequenciaMhz",frequency_mhz(attr(mapping,"RAM_MEMORY_SPEED","Frequência da memória")))
    set_if(specs,"ramMaximaGb",capacity_gb(attr(mapping,"MAX_RAM_MEMORY_CAPACITY","Memória RAM máxima")))
    storage=capacity_gb(attr(mapping,"STORAGE_CAPACITY","Capacidade de armazenamento")) or text_capacity(text,r"\b(\d+(?:[.,]\d+)?\s*(?:GB|TB))\s+(?:SSD|NVMe|HDD)\b"); set_if(specs,"armazenamentoGb",storage)
    stype=attr(mapping,"STORAGE_TYPE","Tipo de armazenamento")
    if not stype:
        stype=first_match(text,r"\b(SSD\s+NVMe|SSD|HDD)\b")
    set_if(specs,"tipoArmazenamento",stype)
    set_if(specs,"tamanhoTelaPolegadas",number(attr(mapping,"SCREEN_SIZE","Tamanho da tela")) or text_number(text,r"\b([0-9]{2}(?:[.,][0-9])?)\s*(?:\"|pol(?:egadas?)?)"))
    res=resolution(attr(mapping,"SCREEN_RESOLUTION","Resolução da tela") or first_match(text,r"\b(\d{3,5}\s*[x×]\s*\d{3,5})\b"))
    if res and "x" in res:
        w,h=res.split("x"); specs["resolucaoLargura"]=int(w); specs["resolucaoAltura"]=int(h)
    set_if(specs,"taxaAtualizacaoHz",integer(attr(mapping,"REFRESH_RATE","Taxa de atualização")) or text_integer(text,r"\b(\d{2,4})\s*Hz\b"))
    set_if(specs,"tipoPainel",attr(mapping,"PANEL_TYPE","Tipo de painel") or first_match(text,r"\b(IPS|VA|TN|OLED|Mini[- ]LED)\b"))
    set_if(specs,"brilhoNits",integer(attr(mapping,"BRIGHTNESS","Brilho")))
    set_if(specs,"bateriaWh",number(attr(mapping,"BATTERY_CAPACITY","Capacidade da bateria")) or text_number(text,r"([0-9.,]+)\s*Wh\b"))
    weight=number(attr(mapping,"WEIGHT","Peso"))
    if weight is not None:
        raw=attr(mapping,"WEIGHT","Peso") or ""; specs["pesoKg"]=round(weight/1000,3) if re.search(r"\bg\b",raw,re.I) and not re.search(r"kg",raw,re.I) else weight
    set_if(specs,"wifi",attr(mapping,"WI_FI","Wi-Fi"))
    set_if(specs,"bluetooth",attr(mapping,"BLUETOOTH","Bluetooth"))
    set_if(specs,"sistemaOperacional",attr(mapping,"OPERATING_SYSTEM","Sistema operacional"))
    if re.search(r"\bwebcam\b|c[aâ]mera\s+HD",text or "",re.I): specs["webcam"]=True
    if re.search(r"teclado\s+(?:retro)?iluminado|backlit\s+keyboard",text or "",re.I): specs["tecladoIluminado"]=True
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
