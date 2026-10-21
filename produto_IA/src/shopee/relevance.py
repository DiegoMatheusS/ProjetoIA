"""Filtra pelo produto principal, sem tratar uma menção como identidade do anúncio."""
import re
import unicodedata


def normalized(text):
    value = unicodedata.normalize('NFKD', str(text or '').casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    # Modelos e capacidades podem vir juntos ou separados no título.
    value = re.sub(r'\b(rtx|gtx|rx|gt|ryzen|ddr)\s*(\d+)', r'\1 \2', value)
    value = re.sub(r'(\b(?:rtx|gtx|rx|gt)\s+\d{3,4})\s*(ti|super|xtx|xt|gre)\b', r'\1 \2', value)
    value = re.sub(r'\b(full|ultra|quad)\s*hd\b', lambda m: {'full': 'fhd', 'ultra': 'uhd', 'quad': 'qhd'}[m.group(1)], value)
    value = re.sub(r'(\d)\s*(gb|tb|mb|mhz|ghz|hz|watts?|w)\b', r'\1 \2', value)
    return value


# A primeira identidade no título costuma ser o que está à venda: "cabo para
# monitor" é cabo; "monitor com cabo" é monitor. Frases específicas precedem
# nomes que aparecem dentro delas (mousepad/mouse, placa-mãe/placa etc.).
INTENTS = (
    ('SUPPORT', r'\b(?:suportes?|apoios?|brackets?|braco\s+(?:articulado|para)|base\s+para)\b'),
    ('CABLE', r'\b(?:cabos?|risers?|extensor(?:es)?|extensoes)\b'),
    ('ADAPTER', r'\b(?:adaptador(?:es)?|conversor(?:es)?|hubs?|docks?|docking\s+station)\b'),
    ('COVER', r'\b(?:capas?|capinhas?|cases?\s+(?:para|de)|bolsas?|peliculas?|protetor(?:es)?)\b'),
    ('PASTE', r'\b(?:pasta\s+termica|thermal\s+paste|thermal\s+pad)\b'),
    ('BATTERY', r'\b(?:baterias?|pilhas?)\b'),
    ('CHARGER', r'\b(?:carregador(?:es)?|fonte\s+(?:para|de)\s+(?:notebook|laptop|celular))\b'),
    ('KIT', r'\b(?:kit\s+(?:upgrade|atualizacao|placa[ -]?mae|processador|ryzen)|combo\s+(?:upgrade|placa[ -]?mae|processador|ryzen))\b'),
    ('PC', r'\b(?:pc(?!\s+case\b)(?:\s+(?:gamer|montado|completo))?|computador(?:es)?|desktop)\b'),
    ('NOTEBOOK', r'\b(?:notebooks?|laptops?|macbooks?)\b'),
    ('MOTHERBOARD', r'\b(?:placas?[ -]?mae|motherboards?)\b'),
    ('GPU', r'\b(?:placas?\s+(?:de\s+)?video|gpu|geforce|radeon|(?:rtx|gtx|rx|gt)\s*\d{3,4}|arc\s+[ab]\d{3})\b'),
    ('CPU', r'\b(?:processador(?:es)?|cpu|ryzen|(?:core\s+)?i[3579](?:[ -]\d{3,5}[a-z]*)?|xeon|athlon|celeron|pentium)\b'),
    ('MEMORY_CARD', r'\b(?:cartao\s+(?:de\s+)?memoria|micro\s*sd|sd\s*card)\b'),
    ('USB_DRIVE', r'\b(?:pen\s*drive|usb\s+flash\s+drive)\b'),
    ('RAM', r'\b(?:memorias?(?:\s+ram)?|ram|ddr\s*[345])\b'),
    ('SSD', r'\b(?:ssd|nvme)\b'),
    ('HDD', r'\b(?:hdd|hd|disco\s+rigido|hard\s+drive)\b'),
    ('CASE', r'\b(?:gabinetes?|computer\s+case|pc\s+case)\b'),
    ('PSU', r'\b(?:fontes?(?:\s+(?:de\s+)?alimentacao)?|psu|power\s+supply)\b'),
    ('COOLER', r'\b(?:water\s*cooler|air\s*cooler|coolers?|waterblocks?|dissipador(?:es)?|heatsinks?)\b'),
    ('FAN', r'\b(?:ventoinhas?|fans?)\b'),
    ('MONITOR', r'\b(?:monitor(?:es)?)\b'),
    ('TV', r'\b(?:televisor(?:es)?|televisao|smart\s*tv|tv)\b'),
    ('MOUSEPAD', r'\b(?:mouse\s*pad|desk\s*mat)\b'),
    ('MOUSE', r'\b(?:mouses?|mouse|ratos?)\b'),
    ('KEYBOARD', r'\b(?:teclados?|keyboards?)\b'),
    ('HEADSET', r'\b(?:headsets?|headphones?|fones?(?:\s+de\s+ouvido)?|earphones?|earbuds?)\b'),
    ('MICROPHONE', r'\b(?:microfones?|microphones?)\b'),
    ('SPEAKER', r'\b(?:caixas?\s+(?:de\s+)?som|alto[ -]?falantes?|speakers?|soundbars?)\b'),
    ('WEBCAM', r'\b(?:webcams?|web\s+camera)\b'),
    ('PHONE', r'\b(?:celular(?:es)?|smartphones?|iphones?)\b'),
    ('TABLET', r'\b(?:tablets?|ipads?)\b'),
    ('CHAIR', r'\b(?:cadeiras?|chairs?)\b'),
    ('CONTROLLER', r'\b(?:controles?|controllers?|gamepads?|joysticks?)\b'),
    ('CONSOLE', r'\b(?:consoles?|playstation|xbox|nintendo\s+switch)\b'),
    ('PRINTER', r'\b(?:impressoras?|printers?)\b'),
    ('ROUTER', r'\b(?:roteador(?:es)?|routers?)\b'),
)
PATTERNS = {kind: re.compile(pattern) for kind, pattern in INTENTS}
STOP_WORDS = set('de da do das dos para por com em e ou um uma o a os as ao no na the for of and novo nova novos novas produto produtos original originais oferta ofertas comprar'.split())
ALIASES = {'gaming': 'gamer', 'wireless': 'semfio', 'fio': 'fio', 'mecanico': 'mecanica', 'mecanicos': 'mecanica', 'mecanicas': 'mecanica', 'watts': 'w', 'watt': 'w'}


def _signals(text):
    return sorted((match.start(), order, kind, match) for order, (kind, _) in enumerate(INTENTS)
                  for match in PATTERNS[kind].finditer(text))


def search_intent(query):
    signals = _signals(normalized(query))
    return signals[0][2] if signals else None


def _words(text):
    text = re.sub(r'\bsem\s+fio\b', 'semfio', text)
    result = set()
    for word in re.findall(r'[a-z0-9]+', text):
        if word not in STOP_WORDS:
            word = ALIASES.get(word, word)
            if len(word) > 4 and word.endswith('s'):
                word = word[:-1]
            result.add(word)
    return result


def relevant_item(item, query, intent=None):
    wanted = normalized(query)
    if not wanted.strip():
        return True  # Resolução por IDs não depende do nome do anúncio.
    title = normalized(item.get('nome'))
    intent = intent or search_intent(wanted)
    title_signals = _signals(title)
    if intent and (not title_signals or title_signals[0][2] != intent):
        return False

    if not intent and title_signals and title_signals[0][2] in {'SUPPORT', 'CABLE', 'ADAPTER', 'COVER', 'PASTE', 'BATTERY', 'CHARGER', 'KIT'}:
        # Também vale para nomes fora da lista de categorias: cabo/capa para
        # uma cafeteira não deve passar numa consulta pela cafeteira.
        occurrences = [m.start() for word in _words(wanted)
                       for m in re.finditer(r'\b' + re.escape(word) + r'\b', title)]
        if not occurrences or title_signals[0][0] < min(occurrences):
            return False

    # Um suporte para GPU não é um suporte para monitor. Da mesma forma, um PC
    # pedido com Ryzen precisa mencionar Ryzen, mesmo que o produto principal
    # seja o computador. Aliases da mesma categoria são intercambiáveis.
    for kind in {signal[2] for signal in _signals(wanted)} - {intent}:
        if not PATTERNS[kind].search(title):
            return False

    # A família/modelo e os sufixos da GPU distinguem variantes diferentes.
    model = re.search(r'\b(rtx|gtx|rx|gt)\s*(\d{3,4})(?:\s*(ti|super|xtx|xt|gre))?\b', wanted)
    if model:
        signature = model.group(1) + r'\s*' + model.group(2)
        signature += r'\s*' + model.group(3) if model.group(3) else r'(?!\s*(?:ti|super|xtx|xt|gre)\b)'
        if not re.search(r'\b' + signature + r'\b', title):
            return False

    # Retira só os nomes de categorias; os qualificadores continuam obrigatórios.
    # Números/modelos preservados abaixo impedem "SSD 1 TB" de aceitar 480 GB,
    # "DDR4" de aceitar DDR5 e "G502" de aceitar qualquer mouse Logitech.
    models = {word for word in _words(wanted) if any(c.isdigit() for c in word)}
    qualifiers = wanted
    spans = sorted((signal[3].start(), signal[3].end()) for signal in _signals(wanted))
    for start, end in reversed(spans):
        qualifiers = qualifiers[:start] + ' ' * (end - start) + qualifiers[end:]
    required = _words(qualifiers) | models
    return required.issubset(_words(title))
