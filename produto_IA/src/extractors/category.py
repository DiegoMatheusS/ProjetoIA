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

    # Categorias compostas vêm primeiro para que CPU/GPU internas não mudem o destino.
    rules = [
        ("NOTEBOOK", [r"\bnotebook\b", r"\blaptop\b", r"\bultrabook\b"]),
        ("PC_MONTADO", [r"\bpc\s+(?:gamer\s+)?(?:completo|montado)\b", r"\bcomputador\s+(?:gamer\s+)?(?:completo|montado)\b"]),
        ("CELULAR", [r"\bsmartphone\b", r"\bcelular\b", r"\biphone\b", r"\bgalaxy\s+[asz]\d", r"\bredmi\b", r"\bpoco\b", r"\bmoto\s+g\b"]),
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
