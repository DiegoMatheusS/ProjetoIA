import re
from ..utils.normalizers import clean_text


def attrs_map(attributes):
    out = {}
    for attr in attributes or []:
        aid = clean_text(attr.get("id"))
        name = clean_text(attr.get("name"))
        value = clean_text(attr.get("value_name"))
        if value:
            if aid:
                out[aid.casefold()] = value
            if name:
                out[name.casefold()] = value
    return out


def find_attr(m, *names):
    for name in names:
        v = m.get(name.casefold())
        if v:
            return v
    return None


def number(value, pattern=r"([0-9]+(?:[.,][0-9]+)?)"):
    if not value:
        return None
    match = re.search(pattern, value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def integer(value):
    n = number(value)
    return int(n) if n is not None else None


def extract_specs(category: str | None, attributes):
    if not category:
        return {}
    m = attrs_map(attributes)
    specs = {}

    if category == "PROCESSADOR":
        socket = find_attr(m, "SOCKET", "Socket", "Soquete")
        cores = integer(find_attr(m, "CORES_NUMBER", "Quantidade de núcleos", "Número de núcleos"))
        threads = integer(find_attr(m, "THREADS_NUMBER", "Quantidade de threads", "Número de threads"))
        base = number(find_attr(m, "CLOCK_SPEED", "Frequência base", "Velocidade do processador"))
        turbo = number(find_attr(m, "MAX_TURBO_FREQUENCY", "Frequência turbo máxima", "Frequência máxima"))
        tdp = integer(find_attr(m, "THERMAL_DESIGN_POWER", "TDP", "Potência de design térmico"))
        memory = find_attr(m, "RAM_MEMORY_TYPE", "Tipos de memória RAM suportados", "Tipo de memória RAM")
        graphics = find_attr(m, "INTEGRATED_GRAPHICS", "Modelo de gráficos integrado", "GPU integrada")
        if socket: specs["socket"] = socket.upper().replace("SOCKET ", "")
        if cores is not None: specs["nucleos"] = cores
        if threads is not None: specs["threads"] = threads
        if base is not None:
            specs["frequenciaBaseMhz"] = int(base * 1000 if base < 100 else base)
        if turbo is not None:
            specs["frequenciaTurboMhz"] = int(turbo * 1000 if turbo < 100 else turbo)
        if tdp is not None: specs["tdpWatts"] = tdp
        if memory:
            types = re.findall(r"DDR[345]", memory.upper())
            if types: specs["tiposMemoriaSuportados"] = list(dict.fromkeys(types))
        if graphics:
            specs["possuiVideoIntegrado"] = graphics.casefold() not in {"não", "nao", "no", "não possui"}
            specs["modeloVideoIntegrado"] = graphics

    elif category == "TECLADO":
        switch = find_attr(m, "KEYBOARD_SWITCH", "Switch", "Tipo de switch")
        layout = find_attr(m, "KEYBOARD_LAYOUT", "Layout")
        connection = find_attr(m, "CONNECTION_TYPE", "Tipo de conexão", "Conectividade")
        if switch: specs["switch"] = switch
        if layout: specs["layout"] = layout
        if connection:
            specs["conexao"] = connection
            specs["usb"] = "usb" in connection.casefold()
            specs["bluetooth"] = "bluetooth" in connection.casefold()
            specs["wireless"] = any(x in connection.casefold() for x in ("wireless", "sem fio", "2.4"))

    return specs
