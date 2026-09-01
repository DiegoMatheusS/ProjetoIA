import re
import unicodedata


def _clean(value: str):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.casefold()


ALIASES = {
    "CPU": "PROCESSADOR",
    "PROCESSADORES": "PROCESSADOR",
    "PLACA-MAE": "PLACA_MAE",
    "PLACAMAE": "PLACA_MAE",
    "MOTHERBOARD": "PLACA_MAE",
    "RAM": "MEMORIA_RAM",
    "MEMORIA": "MEMORIA_RAM",
    "GPU": "PLACA_VIDEO",
    "PLACA DE VIDEO": "PLACA_VIDEO",
    "SSD": "ARMAZENAMENTO",
    "HDD": "ARMAZENAMENTO",
    "PSU": "FONTE",
    "CASE": "GABINETE",
    "FAN": "VENTOINHA",
    "HEADSET": "HEADSET",
    "FONES": "FONE",
    "SMARTPHONE": "CELULAR",
    "PC MONTADO": "PC_MONTADO",
    "PC-MONTADO": "PC_MONTADO",
    "SUPORTE DE MONITOR": "SUPORTE_MONITOR",
    "PROJETOR": "PROJETOR",
    "TABLET": "TABLET",
    "ROTEADOR": "ROTEADOR",
    "NOBREAK": "NOBREAK",
    "SMARTWATCH": "RELOGIO_INTELIGENTE",
    "VIDEO GAME": "VIDEO_GAME",
    "VIDEOGAME": "VIDEO_GAME",
    "BRACO MONITOR": "SUPORTE_MONITOR",
}


def normalize_forced(value: str):
    raw = (value or "").strip().upper().replace("-", " ")
    raw = re.sub(r"\s+", " ", raw)
    return ALIASES.get(raw, raw.replace(" ", "_"))


def detect_category(text: str, forced: str | None = None):
    if forced:
        return normalize_forced(forced)

    t = _clean(text)

    # Quando recebemos o título do produto, o início da frase é a evidência mais
    # forte da categoria. Isso evita falsos positivos de termos citados na ficha
    # (ex.: uma ventoinha menciona "placa-mãe" e "notebook" na descrição).
    headline = t[:320]
    headline_rules = [
        ("VENTOINHA", [r"^\s*(?:kit\s+com\s+\d+\s+)?ventoinhas?\b", r"^\s*fans?\b"]),
        ("NOTEBOOK", [r"^\s*notebook\b", r"^\s*laptop\b", r"^\s*ultrabook\b"]),
        ("PC_MONTADO", [r"^\s*(?:pc|computador)\s+gamer\b", r"^\s*(?:pc|computador)\s+(?:gamer\s+)?(?:completo|montado)\b", r"^\s*desktop\s+(?:gamer|montado)\b"]),
        ("PLACA_MAE", [r"^\s*placa[- ]mae\b", r"^\s*motherboard\b"]),
        ("PLACA_VIDEO", [r"^\s*placa\s+de\s+video\b", r"^\s*(?:gpu|geforce|radeon)\b"]),
        ("PROCESSADOR", [r"^\s*processador\b", r"^\s*cpu\b"]),
        ("MEMORIA_RAM", [r"^\s*memoria\s+ram\b", r"^\s*kit\s+de\s+memoria\b"]),
        ("ARMAZENAMENTO", [r"^\s*(?:ssd|hdd|hd\s+)\b"]),
        ("FONTE", [r"^\s*fonte\b", r"^\s*power\s+supply\b"]),
        ("GABINETE", [r"^\s*gabinete\b", r"^\s*computer\s+case\b"]),
        ("COOLER", [r"^\s*(?:water|air)\s*cooler\b", r"^\s*cooler\b"]),
        ("MONITOR", [r"^\s*monitor\b"]),
        ("TECLADO", [r"^\s*teclado\b", r"^\s*keyboard\b"]),
        ("MOUSE", [r"^\s*mouse\b"]),
        ("HEADSET", [r"^\s*headset\b"]),
        ("FONE", [r"^\s*(?:fone|headphone|earbuds?)\b"]),
        ("MICROFONE", [r"^\s*(?:microfone|microphone)\b"]),
    ]
    for category, patterns in headline_rules:
        if any(re.search(pattern, headline, re.I | re.S) for pattern in patterns):
            return category

    # Categorias compostas vêm primeiro para que CPU/GPU internas não mudem o destino.
    rules = [
        ("NOTEBOOK", [r"\bnotebook\b", r"\blaptop\b", r"\bultrabook\b"]),
        ("PC_MONTADO", [r"\bpc\s+gamer\b", r"\bcomputador\s+gamer\b", r"\bpc\s+(?:gamer\s+)?(?:completo|montado)\b", r"\bcomputador\s+(?:gamer\s+)?(?:completo|montado)\b", r"\bdesktop\s+(?:gamer|montado)\b"]),
        ("CELULAR", [r"\bsmartphone\b", r"\bcelular\b", r"\biphone\b", r"\bgalaxy\s+[asz]\d", r"\bredmi\b", r"\bpoco\b", r"\bmoto\s+g\b"]),
        ("PROJETOR", [r"\bprojetor\b", r"\bprojector\b"]),
        ("CALCULADORA", [r"\bcalculadora\b"]),
        ("TELEFONE", [r"\btelefone\b(?:\s+sem\s+fio|\s+fixo)?"]),
        ("IMPRESSORA_3D", [r"\bimpressora\s+3d\b"]),
        ("IMPRESSORA", [r"\bimpressora\b", r"\bprinter\b"]),
        ("SCANNER", [r"\bscanner\b"]),
        ("CAIXA_DE_SOM", [r"\bcaixa\s+de\s+som\b", r"\bspeaker\b"]),
        ("ROTEADOR", [r"\broteador\b", r"\brouter\b"]),
        ("REPETIDOR_WIFI", [r"\brepetidor\b.{0,20}\bwi-?fi\b"]),
        ("SWITCH_REDE", [r"\bswitch\b.{0,20}\brede\b"]),
        ("NOBREAK", [r"\bnobreak\b", r"\bups\b"]),
        ("ESTABILIZADOR", [r"\bestabilizador\b"]),
        ("FILTRO_DE_LINHA", [r"\bfiltro\s+de\s+linha\b"]),
        ("TABLET", [r"\btablet\b", r"\bipad\b"]),
        ("MICROCONTROLADOR", [r"\bmicrocontrolador\b", r"\besp32\b", r"\besp8266\b", r"\barduino\b"]),
        ("MINI_COMPUTADOR", [r"\bmini\s*(?:pc|computador)\b", r"\bras?pb?erry\s+pi\b"]),
        ("RELOGIO_INTELIGENTE", [r"\bsmartwatch\b", r"\brelogio\s+inteligente\b"]),
        ("VOLANTE", [r"\bvolante\b.{0,25}\b(?:gamer|jogo|simulador)\b"]),
        ("JOYSTICK", [r"\bjoystick\b"]),
        ("CONTROLE_VIDEO_GAME", [r"\bcontrole\b.{0,30}\b(?:xbox|playstation|ps[345]|switch|videogame|console)\b", r"\bgamepad\b"]),
        ("VIDEO_GAME", [r"\b(?:videogame|console)\b", r"\bplaystation\s*[345]\b", r"\bxbox\b", r"\bnintendo\s+switch\b"]),
        ("SMART_TV", [r"\bsmart\s*tv\b"]),
        ("CAMERA", [r"\bcamera\b.{0,20}\b(?:digital|mirrorless|dslr)\b"]),
        ("POWER_BANK", [r"\bpower\s*bank\b"]),
        ("HUB_USB", [r"\bhub\s+usb\b"]),
        ("DOCK_STATION", [r"\bdock(?:ing)?\s+station\b"]),
        ("PEN_DRIVE", [r"\bpen\s*drive\b"]),
        ("CARTAO_MEMORIA", [r"\bcartao\s+de\s+memoria\b", r"\bmicrosd\b"]),
        ("ARMAZENAMENTO_EXTERNO", [r"\b(?:hd|ssd)\s+externo\b"]),
        ("SUPORTE_MONITOR", [r"\b(?:suporte|braco)\b.{0,30}\bmonitor\b"]),
        ("WEBCAM", [r"\bwebcam\b", r"camera\s+para\s+pc"]),
        ("CONTROLE", [r"\bcontrole\s+(?:sem\s+fio|gamer|bluetooth|para\s+pc)\b", r"\bgamepad\b"]),
        ("CADEIRA", [r"\bcadeira\s+(?:gamer|ergonomica|escritorio)\b"]),
        ("MOUSEPAD", [r"\bmouse\s*pad\b", r"\bmousepad\b"]),
        ("MESA", [r"\bmesa\s+(?:gamer|escritorio|computer)\b"]),
        ("ILUMINACAO", [r"\bfita\s+led\b", r"\biluminacao\s+(?:rgb|led)\b", r"\blight\s*bar\b"]),
        ("ORGANIZADOR_CABOS", [r"\borganizador(?:es)?\s+de\s+cabos?\b", r"\bcable\s+management\b"]),
        ("ACESSORIO", [r"\bacess[oó]rio\s+(?:para\s+pc|gamer|de\s+setup)\b"]),
        ("PLACA_MAE", [r"placa[- ]mae", r"\bmotherboard\b"]),
        ("PLACA_VIDEO", [r"placa de video", r"\bgeforce\b", r"\bradeon\s+rx\b", r"\brtx\s*\d", r"\brx\s*\d"]),
        ("PROCESSADOR", [r"\bprocessador\b", r"\bryzen\b", r"\bcore\s+(?:ultra\s+)?i?[3579]\b", r"\bintel\s+core\b"]),
        ("MEMORIA_RAM", [r"memoria\s+ram", r"\b(?:ddr[345])\b.{0,40}\b(?:4|8|16|24|32|48|64|96|128)\s*gb\b"]),
        ("ARMAZENAMENTO", [r"\bssd\b", r"\bnvme\b", r"\bhdd\b", r"disco\s+rigido"]),
        ("FONTE", [r"\bfonte\b.{0,45}\b\d{3,4}\s*w\b", r"\bpower\s+supply\b", r"\bpsu\b"]),
        ("GABINETE", [r"\bgabinete\b", r"\bcomputer\s+case\b", r"\bpc\s+case\b"]),
        ("COOLER", [r"\bwater\s*cooler\b", r"\bair\s*cooler\b", r"\baio\s+\d{3}\b", r"cooler.{0,20}\bcpu\b"]),
        ("VENTOINHA", [r"\bventoinha\b", r"\bcooler\s+fan\b", r"\bfan\s+(?:rgb|argb|pwm|120|140)\b"]),
        ("MONITOR", [r"\bmonitor\b"]),
        ("TECLADO", [r"\bteclado\b", r"\bkeyboard\b"]),
        ("MOUSE", [r"\bmouse\b"]),
        ("HEADSET", [r"\bheadset\b"]),
        ("FONE", [r"\bfone\b", r"\bheadphone\b", r"\bearbuds?\b"]),
        ("MICROFONE", [r"\bmicrofone\b", r"\bmicrophone\b"]),
    ]

    for category, patterns in rules:
        if any(re.search(pattern, t, re.I | re.S) for pattern in patterns):
            return category
    return None
