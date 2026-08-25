import re


def detect_category(text: str, forced: str | None = None):
    if forced:
        return forced.upper()
    t = (text or "").casefold()
    rules = [
        ("PROCESSADOR", [r"\bprocessador\b", r"\bryzen\b", r"\bcore\s+i[3579]\b"]),
        ("PLACA_VIDEO", [r"placa de v[ií]deo", r"geforce", r"radeon rx", r"\brtx\s*\d", r"\brx\s*\d"]),
        ("PLACA_MAE", [r"placa[- ]m[aã]e", r"motherboard"]),
        ("MEMORIA_RAM", [r"mem[oó]ria ram", r"\b(ddr[345])\b.*\b(8|16|32|64)\s*gb"]),
        ("ARMAZENAMENTO", [r"\bssd\b", r"\bnvme\b", r"\bhdd\b", r"disco r[ií]gido"]),
        ("FONTE", [r"fonte .*\b\d{3,4}\s*w\b", r"power supply"]),
        ("GABINETE", [r"\bgabinete\b", r"computer case"]),
        ("COOLER", [r"water cooler", r"air cooler", r"cooler.*cpu"]),
        ("VENTOINHA", [r"ventoinha", r"\bfan\b"]),
        ("MONITOR", [r"\bmonitor\b"]),
        ("TECLADO", [r"\bteclado\b"]),
        ("MOUSE", [r"\bmouse\b"]),
        ("FONE", [r"\bheadset\b", r"\bfone\b"]),
        ("MICROFONE", [r"\bmicrofone\b"]),
    ]
    for category, patterns in rules:
        if any(re.search(p, t, re.I) for p in patterns):
            return category
    return None
