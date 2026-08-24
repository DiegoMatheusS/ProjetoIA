const { SCHEMAS, ENUMS } = require('./backend-schemas');

function primeiroMatch(texto, regex, transform = (v) => v) {
  const m = String(texto || '').match(regex);
  return m?.[1] != null ? transform(m[1]) : undefined;
}

function numeroPt(v) {
  const texto = String(v).replace(/\./g, '').replace(',', '.');
  const n = Number(texto);
  return Number.isFinite(n) ? n : undefined;
}

function numeroSimples(v) {
  const n = Number(String(v).replace(',', '.'));
  return Number.isFinite(n) ? n : undefined;
}

function booleanoPresenca(texto, positivo, negativo) {
  const fonte = String(texto || '');
  if (negativo && negativo.test(fonte)) return false;
  if (positivo.test(fonte)) return true;
  return undefined;
}

function linhas(texto) {
  return String(texto || '')
    .split(/\r?\n/)
    .map((linha) => linha.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
}

function escaparRegex(valor) {
  return String(valor).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function limparValorRotulado(valor) {
  return String(valor || '')
    .replace(/^\s*[|:;\-–—]+\s*/, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function extrairValorRotulado(texto, rotulos) {
  const fonte = String(texto || '');
  const lista = linhas(fonte);

  for (const linhaOriginal of lista) {
    const linha = limparValorRotulado(linhaOriginal);
    for (const rotulo of rotulos) {
      const r = escaparRegex(rotulo);
      const padroes = [
        new RegExp(`^${r}\\s*(?:\\||:|;|\\-|–|—)\\s*(.+?)$`, 'i'),
        new RegExp(`^${r}\\s+(.+?)$`, 'i'),
      ];
      for (const regex of padroes) {
        const match = linha.match(regex);
        if (match?.[1]) {
          const valor = limparValorRotulado(match[1]);
          if (valor && valor.toLowerCase() !== rotulo.toLowerCase()) return valor;
        }
      }
    }
  }

  for (const rotulo of rotulos) {
    const r = escaparRegex(rotulo);
    const regex = new RegExp(`${r}\\s*(?:\\||:|;|\\-|–|—)\\s*([^|;\\n]+)`, 'i');
    const match = fonte.match(regex);
    if (match?.[1]) {
      const valor = limparValorRotulado(match[1]);
      if (valor) return valor;
    }
  }

  return undefined;
}

function listaRotulada(texto, rotulos) {
  const valor = extrairValorRotulado(texto, rotulos);
  if (!valor) return undefined;
  return valor
    .split(/[,/|;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizarTipoMemoria(valor) {
  const encontrados = String(valor || '').match(/DDR[345]/gi) || [];
  return [...new Set(encontrados.map((v) => v.toUpperCase()))].filter((v) => ENUMS.TipoMemoria.includes(v));
}

function normalizarFormatoPlacaMae(valor) {
  const texto = String(valor || '').toUpperCase().replace(/\s+/g, '_').replace('-', '_');
  const mapa = {
    E_ATX: 'E_ATX',
    EATX: 'E_ATX',
    ATX: 'ATX',
    MICRO_ATX: 'MICRO_ATX',
    MATX: 'MICRO_ATX',
    MINI_ITX: 'MINI_ITX',
    MINITX: 'MINI_ITX',
  };
  return mapa[texto];
}

function normalizarFormatoFonte(valor) {
  const texto = String(valor || '').toUpperCase().replace(/\s+/g, '_').replace('-', '_');
  if (texto.includes('SFX_L')) return 'SFX_L';
  if (texto === 'SFX') return 'SFX';
  if (texto === 'TFX') return 'TFX';
  if (texto === 'FLEX_ATX' || texto === 'FLEX') return 'FLEX_ATX';
  if (texto === 'ATX') return 'ATX';
  return undefined;
}

function extrairSocket(texto) {
  return primeiroMatch(texto, /\b(AM[345]|LGA\s*\d{3,5}|TR4|sTRX4|sTR5)\b/i, (v) => v.replace(/\s+/g, '').toUpperCase());
}

function extrairTeclado(texto) {
  const t = String(texto || '');
  const specs = {};
  const tipoRotulado = extrairValorRotulado(t, ['Tipo Teclado', 'Tipo de Teclado']);

  if (tipoRotulado) {
    const tipo = tipoRotulado.match(/^(Mecânico|Membrana|Semi[- ]?Mecânico)/i)?.[1];
    if (tipo) specs.tipo = tipo.replace(/^semi[- ]?mecânico$/i, 'Semi-Mecânico').replace(/^mecânico$/i, 'Mecânico').replace(/^membrana$/i, 'Membrana');
    const layoutDoTipo = tipoRotulado.match(/(Mini\s*\(\s*\d+%\s*\)|Full\s*Size|TKL|Tenkeyless|\d+%)/i)?.[1];
    if (layoutDoTipo) specs.layout = layoutDoTipo.replace(/\s+/g, ' ').trim();
  }

  if (!specs.tipo) {
    if (/\bteclado\s+mec[aâ]nico\b|\bmec[aâ]nico\b/i.test(t)) specs.tipo = 'Mecânico';
    else if (/\bteclado\s+(?:de\s+)?membrana\b|\bmembrana\b/i.test(t)) specs.tipo = 'Membrana';
  }

  const sw = extrairValorRotulado(t, ['Switch', 'Switches', 'Tipo de Switch']) || primeiroMatch(
    t.split('\n')[0],
    /\bswitch\s+((?:outemu|cherry\s*mx|gateron|kailh|huano|akko)\s+[a-záàâãéêíóôõúü0-9]+)/i,
    (v) => v.trim(),
  );
  if (sw && sw.length <= 100) specs.switch = sw;

  const layoutRotulado = extrairValorRotulado(t, ['Layout']);
  if (layoutRotulado && layoutRotulado.length <= 80) specs.layout = layoutRotulado;
  if (!specs.layout) {
    const layoutPadrao = primeiroMatch(t, /\b(Mini\s*\(\s*\d+%\s*\)|Full\s*Size|TKL|Tenkeyless|\d+%|ABNT2|ABNT\s*2|ANSI|ISO)\b/i, (v) => v.replace(/\s+/g, ' ').trim());
    if (layoutPadrao) specs.layout = layoutPadrao;
  }

  const tamanho = extrairValorRotulado(t, ['Tamanho', 'Formato', 'Size']);
  if (tamanho && tamanho.length <= 80) specs.tamanho = tamanho;

  const abnt2 = booleanoPresenca(t, /\babnt\s*2\b|\babnt2\b/i, /\bn[aã]o\s+(?:é\s+)?abnt\s*2\b/i);
  if (abnt2 !== undefined) specs.abnt2 = abnt2;

  const conexao = extrairValorRotulado(t, ['Tipo de conexão', 'Tipo de conexao', 'Conectividade', 'Conexões', 'Conexoes', 'Conexão', 'Conexao']);
  if (conexao && conexao.length <= 100) specs.conexao = conexao;
  else if (/\bbluetooth\b/i.test(t) && !/\bUSB\b/i.test(t)) specs.conexao = 'Bluetooth';
  else if (/\bUSB[- ]?C\b|\bUSB\s+Tipo\s+C\b/i.test(t)) specs.conexao = 'USB-C';
  else if (/\bUSB\b/i.test(t)) specs.conexao = 'USB';

  const rgb = booleanoPresenca(t, /\brgb\b|\bargb\b/i, /\bsem\s+rgb\b|\bn[aã]o\s+possui\s+rgb\b/i);
  if (rgb !== undefined) specs.rgb = rgb;
  const hotSwap = booleanoPresenca(t, /hot\s*[- ]?swap|hotswap/i, /n[aã]o\s+(?:possui\s+)?hot\s*[- ]?swap/i);
  if (hotSwap !== undefined) specs.hotSwap = hotSwap;
  const bluetooth = booleanoPresenca(t, /\bbluetooth\b/i, /\bsem\s+bluetooth\b|\bn[aã]o\s+possui\s+bluetooth\b/i);
  if (bluetooth !== undefined) specs.bluetooth = bluetooth;
  const wireless = booleanoPresenca(t, /\bwireless\b|\bsem\s+fio\b|\b2\.4\s*ghz\b/i, /\bcom\s+fio\s+apenas\b|\bsomente\s+cabo\b|\bn[aã]o\s+[eé]\s+wireless\b/i);
  if (wireless !== undefined) specs.wireless = wireless;
  const usb = booleanoPresenca(t, /\bUSB(?:[- ]?C|\s+Tipo\s+C)?\b/i, /\bsem\s+USB\b/i);
  if (usb !== undefined) specs.usb = usb;

  return specs;
}

function extrairMouse(texto) {
  const t = String(texto || '');
  const specs = {};
  const sensor = extrairValorRotulado(t, ['Sensor', 'Sensor óptico', 'Sensor optico']);
  if (sensor) specs.sensor = sensor;
  const dpi = primeiroMatch(t, /([\d.]+)\s*dpi/i, (v) => Number(v.replace(/\./g, '')));
  if (dpi) specs.dpiMaximo = dpi;
  const polling = primeiroMatch(t, /(?:polling(?:\s*rate)?|taxa de polling)[^\d]{0,30}(\d+)\s*hz/i, Number) || primeiroMatch(t, /(\d{3,5})\s*hz/i, Number);
  if (polling) specs.pollingRateHz = polling;
  const botoes = primeiroMatch(t, /(\d+)\s*bot[oõ]es/i, Number);
  if (botoes) specs.botoes = botoes;
  const peso = primeiroMatch(t, /(?:peso[^\d]{0,20})?(\d+(?:[.,]\d+)?)\s*g(?:ramas)?\b/i, numeroPt);
  if (peso) specs.pesoGramas = peso;
  const conexao = extrairValorRotulado(t, ['Conexão', 'Conexao', 'Conectividade']);
  if (conexao) specs.conexao = conexao;
  const bluetooth = booleanoPresenca(t, /\bbluetooth\b/i, /\bsem\s+bluetooth\b/i);
  if (bluetooth !== undefined) specs.bluetooth = bluetooth;
  const wireless = booleanoPresenca(t, /\bwireless\b|\b2\.4\s*ghz\b|\bsem\s+fio\b/i, /\bsomente\s+cabo\b/i);
  if (wireless !== undefined) specs.wireless = wireless;
  const cabo = booleanoPresenca(t, /\bcabo\b|\bcab[eé]ado\b/i, /\bsem\s+cabo\b/i);
  if (cabo !== undefined) specs.cabo = cabo;
  const rgb = booleanoPresenca(t, /\brgb\b/i, /\bsem\s+rgb\b/i);
  if (rgb !== undefined) specs.rgb = rgb;
  const mao = extrairValorRotulado(t, ['Mão', 'Mao', 'Mão de uso', 'Mao de uso']);
  if (mao) specs.mao = mao;
  return specs;
}

function extrairMonitor(texto) {
  const t = String(texto || '');
  const specs = {};
  const polegadas = primeiroMatch(t, /(?:tamanho[^\d]{0,20})?(\d+(?:[.,]\d+)?)\s*(?:"|polegadas)/i, numeroPt);
  if (polegadas) specs.tamanhoPolegadas = polegadas;
  const resolucao = extrairValorRotulado(t, ['Resolução', 'Resolucao']) || primeiroMatch(t, /(\d{3,4}\s*[x×]\s*\d{3,4})/i, (v) => v.replace(/\s+/g, '').replace('×', 'x'));
  if (resolucao) specs.resolucao = resolucao;
  const hz = primeiroMatch(t, /(?:taxa(?:\s+de)?\s+atualiza[cç][aã]o|refresh rate)[^\d]{0,30}(\d{2,4})\s*hz/i, Number) || primeiroMatch(t, /(\d{2,4})\s*hz/i, Number);
  if (hz) specs.taxaAtualizacaoHz = hz;
  const ms = primeiroMatch(t, /(?:tempo de resposta|response time)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*ms/i, numeroPt) || primeiroMatch(t, /(\d+(?:[.,]\d+)?)\s*ms/i, numeroPt);
  if (ms) specs.tempoRespostaMs = ms;
  const nits = primeiroMatch(t, /(?:brilho|brightness)[^\d]{0,30}(\d+)\s*nits?/i, Number) || primeiroMatch(t, /(\d+)\s*nits?/i, Number);
  if (nits) specs.brilhoNits = nits;
  const painel = extrairValorRotulado(t, ['Tipo de painel', 'Painel', 'Tipo de tela']) || primeiroMatch(t, /\b(IPS|VA|TN|OLED|Mini[- ]?LED)\b/i, (v) => v.toUpperCase());
  if (painel) specs.tipoPainel = painel;
  const hdr = booleanoPresenca(t, /\bHDR\b/i, /\bsem\s+HDR\b/i);
  if (hdr !== undefined) specs.hdr = hdr;
  const adaptive = booleanoPresenca(t, /adaptive\s*sync/i, /sem\s+adaptive\s*sync/i);
  if (adaptive !== undefined) specs.adaptiveSync = adaptive;
  const gsync = booleanoPresenca(t, /g\s*[- ]?sync/i, /sem\s+g\s*[- ]?sync/i);
  if (gsync !== undefined) specs.gSync = gsync;
  const freesync = booleanoPresenca(t, /free\s*sync|freesync/i, /sem\s+free\s*sync/i);
  if (freesync !== undefined) specs.freeSync = freesync;
  return specs;
}

function extrairMemoriaRam(texto) {
  const t = String(texto || '');
  const specs = {};
  const tipo = primeiroMatch(t, /\b(DDR3|DDR4|DDR5)\b/i, (v) => v.toUpperCase());
  if (tipo) specs.tipo = tipo;
  const formato = /so[- ]?dimm/i.test(t) ? 'SO_DIMM' : /\bdimm\b/i.test(t) ? 'DIMM' : undefined;
  if (formato) specs.formato = formato;
  const kitMatch = t.match(/(?:kit\s*)?(\d+)\s*[xX]\s*(\d+)\s*gb/i);
  if (kitMatch) {
    specs.quantidadeModulos = Number(kitMatch[1]);
    specs.capacidadePorModuloGb = Number(kitMatch[2]);
  } else {
    const capacidade = extrairValorRotulado(t, ['Capacidade por módulo', 'Capacidade', 'Memória', 'Memoria']);
    const gb = primeiroMatch(capacidade || t, /(\d+)\s*gb/i, Number);
    if (gb) {
      specs.quantidadeModulos = 1;
      specs.capacidadePorModuloGb = gb;
    }
  }
  const mhz = primeiroMatch(t, /(?:frequ[eê]ncia|clock)[^\d]{0,20}(\d{3,5})\s*mhz/i, Number) || primeiroMatch(t, /(\d{3,5})\s*mhz/i, Number);
  if (mhz) specs.frequenciaMhz = mhz;
  const jedec = primeiroMatch(t, /(?:jedec)[^\d]{0,20}(\d{3,5})\s*mhz/i, Number);
  if (jedec) specs.frequenciaJedecMhz = jedec;
  const cl = primeiroMatch(t, /\bCL\s*(\d{1,3})\b/i, Number);
  if (cl) specs.latenciaCl = cl;
  const volts = primeiroMatch(t, /(?:tens[aã]o|voltagem)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*v\b/i, numeroPt);
  if (volts) specs.tensaoVolts = volts;
  const ecc = booleanoPresenca(t, /\bECC\b/i, /\bsem\s+ECC\b/i);
  if (ecc !== undefined) specs.ecc = ecc;
  const registrada = booleanoPresenca(t, /\bregistrada\b|\bregistered\b/i, /\bn[aã]o\s+registrada\b|\bunbuffered\b/i);
  if (registrada !== undefined) specs.registrada = registrada;
  const xmp = booleanoPresenca(t, /\bXMP\b/i, /\bsem\s+XMP\b/i);
  if (xmp !== undefined) specs.suportaXmp = xmp;
  const expo = booleanoPresenca(t, /\bEXPO\b/i, /\bsem\s+EXPO\b/i);
  if (expo !== undefined) specs.suportaExpo = expo;
  const altura = primeiroMatch(t, /(?:altura|height)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (altura) specs.alturaMm = altura;
  const rgb = booleanoPresenca(t, /\brgb\b/i, /\bsem\s+rgb\b/i);
  if (rgb !== undefined) specs.rgb = rgb;
  return specs;
}

function extrairArmazenamento(texto) {
  const t = String(texto || '');
  const specs = {};
  if (/\bSSD\b/i.test(t)) specs.tipo = 'SSD';
  else if (/\bHDD\b|disco r[ií]gido/i.test(t)) specs.tipo = 'HDD';
  if (/m\.2/i.test(t)) specs.formato = 'M2';
  else if (/2[.,]5\s*(?:"|polegadas)/i.test(t)) specs.formato = 'POLEGADAS_2_5';
  else if (/3[.,]5\s*(?:"|polegadas)/i.test(t)) specs.formato = 'POLEGADAS_3_5';
  else if (/placa\s+pcie|add[- ]in\s+card/i.test(t)) specs.formato = 'PLACA_PCIE';
  if (/nvme|pcie/i.test(t)) specs.interface = 'NVME_PCIE';
  else if (/\bsata\b/i.test(t)) specs.interface = 'SATA';
  else if (/\bsas\b/i.test(t)) specs.interface = 'SAS';
  const tb = primeiroMatch(t, /(\d+(?:[.,]\d+)?)\s*tb\b/i, numeroPt);
  const gb = primeiroMatch(t, /(\d+)\s*gb\b/i, Number);
  if (tb) specs.capacidadeGb = Math.round(tb * 1000);
  else if (gb) specs.capacidadeGb = gb;
  const m2 = primeiroMatch(t, /(?:M\.2|tamanho M\.2)[^\d]{0,20}(2230|2242|2260|2280|22110)/i, Number);
  if (m2) specs.tamanhoM2Mm = m2;
  const chave = primeiroMatch(t, /(?:chave|key)[^A-Z]*(B_M|B\/M|B\+M|B|M)\b/i, (v) => v.toUpperCase().replace(/[+/]/g, '_'));
  if (chave === 'B_M' || chave === 'B' || chave === 'M') specs.chaveM2 = chave;
  const gen = primeiroMatch(t, /(?:PCIe|PCI-Express)\s*(?:Gen(?:era[cç][aã]o)?\s*)?(\d)/i, Number);
  if (gen) specs.geracaoPcie = gen;
  const lanes = primeiroMatch(t, /(?:x|×)\s*(\d+)\b/i, Number);
  if (lanes && lanes <= 16) specs.pistasPcie = lanes;
  const leitura = primeiroMatch(t, /(?:leitura|read)[^\d]{0,40}(\d{3,6})\s*mb\/s/i, Number);
  if (leitura) specs.leituraSequencialMbps = leitura;
  const escrita = primeiroMatch(t, /(?:grava[cç][aã]o|escrita|write)[^\d]{0,40}(\d{3,6})\s*mb\/s/i, Number);
  if (escrita) specs.escritaSequencialMbps = escrita;
  const dissipador = booleanoPresenca(t, /dissipador|heatsink/i, /sem\s+dissipador/i);
  if (dissipador !== undefined) specs.possuiDissipador = dissipador;
  return specs;
}

function extrairFonte(texto) {
  const t = String(texto || '');
  const specs = {};
  const formato = normalizarFormatoFonte(extrairValorRotulado(t, ['Formato', 'Form Factor']) || primeiroMatch(t, /\b(ATX|SFX-L|SFX|TFX|FLEX[- ]?ATX)\b/i));
  if (formato) specs.formato = formato;
  const watts = primeiroMatch(t, /(?:pot[eê]ncia|power)[^\d]{0,30}(\d{3,5})\s*w(?:atts?)?\b/i, Number) || primeiroMatch(t, /(\d{3,5})\s*w(?:atts?)?\b/i, Number);
  if (watts) specs.potenciaWatts = watts;
  const cert = extrairValorRotulado(t, ['Certificação', 'Certificacao', 'Certificação 80 Plus', 'Certificacao 80 Plus']) || primeiroMatch(t, /(80\s*plus\s*(?:white|bronze|silver|gold|platinum|titanium)?)/i, (v) => v.replace(/\s+/g, ' ').trim());
  if (cert) specs.certificacao = cert;
  if (/semi[- ]?modular/i.test(t)) specs.modularidade = 'SEMI_MODULAR';
  else if (/n[aã]o[- ]?modular/i.test(t)) specs.modularidade = 'NAO_MODULAR';
  else if (/\bmodular\b/i.test(t)) specs.modularidade = 'MODULAR';
  const eficiencia = primeiroMatch(t, /(?:efici[eê]ncia|efficiency)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*%/i, numeroPt);
  if (eficiencia) specs.eficienciaPercentual = eficiencia;
  const linha12 = primeiroMatch(t, /(?:linha\s*12v|12v)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*a\b/i, numeroPt);
  if (linha12) specs.correnteLinha12vAmperes = linha12;
  const tamanho = (campo, rotulos) => {
    const valor = primeiroMatch(t, new RegExp(`(?:${rotulos.join('|')})[^\\d]{0,20}(\\d+(?:[.,]\\d+)?)\\s*mm`, 'i'), numeroPt);
    if (valor) specs[campo] = valor;
  };
  tamanho('comprimentoMm', ['comprimento', 'depth']);
  tamanho('larguraMm', ['largura', 'width']);
  tamanho('alturaMm', ['altura', 'height']);
  const conectores = [
    ['conectoresAtx24Pinos', /(?:ATX\s*24|24\s*pinos)[^\d]{0,20}(\d+)/i],
    ['conectoresEpsCpu', /(?:EPS|CPU)[^\d]{0,20}(\d+)\s*(?:conector|conectores)?/i],
    ['conectoresPcie6Pinos', /(?:PCIe|PCI-E)[^\d]{0,10}6\s*pinos[^\d]{0,10}(\d+)/i],
    ['conectoresPcie8Pinos', /(?:PCIe|PCI-E)[^\d]{0,10}8\s*pinos[^\d]{0,10}(\d+)/i],
    ['conectores12vhpwr', /12VHPWR[^\d]{0,10}(\d+)/i],
    ['conectores12v2x6', /12V-2x6|12V2x6[^\d]{0,10}(\d+)/i],
    ['conectoresSata', /(?:SATA)[^\d]{0,10}(\d+)\s*(?:conector|conectores)?/i],
    ['conectoresMolex', /(?:Molex)[^\d]{0,10}(\d+)\s*(?:conector|conectores)?/i],
  ];
  for (const [campo, regex] of conectores) {
    const valor = primeiroMatch(t, regex, Number);
    if (valor !== undefined) specs[campo] = valor;
  }
  const tensao = extrairValorRotulado(t, ['Tensão de entrada', 'Tensao de entrada', 'Entrada']);
  if (tensao) specs.tensaoEntrada = tensao;
  return specs;
}

function extrairProcessador(texto) {
  const t = String(texto || '');
  const specs = {};
  const socket = extrairSocket(t);
  if (socket) specs.socket = socket;
  const familia = extrairValorRotulado(t, ['Família', 'Familia']);
  if (familia) specs.familia = familia;
  const linha = extrairValorRotulado(t, ['Linha']);
  if (linha) specs.linha = linha;
  const geracao = extrairValorRotulado(t, ['Geração', 'Geracao']);
  if (geracao) specs.geracao = geracao;
  const arquitetura = extrairValorRotulado(t, ['Arquitetura']);
  if (arquitetura) specs.arquitetura = arquitetura;
  const litografia = primeiroMatch(t, /(?:litografia|processo)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*nm/i, numeroPt);
  if (litografia) specs.litografiaNm = litografia;
  const cores = primeiroMatch(t, /(?:núcleos|nucleos|cores)[^\d]{0,15}(\d+)/i, Number);
  if (cores) specs.nucleos = cores;
  const threads = primeiroMatch(t, /threads?[^\d]{0,15}(\d+)/i, Number);
  if (threads) specs.threads = threads;
  const base = primeiroMatch(t, /(?:frequ[eê]ncia\s*base|base\s*clock)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*(ghz|mhz)/i, (v) => v);
  if (base) {
    const m = t.match(/(?:frequ[eê]ncia\s*base|base\s*clock)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*(ghz|mhz)/i);
    specs.frequenciaBaseMhz = m?.[2].toLowerCase() === 'ghz' ? Math.round(Number(m[1].replace(',', '.')) * 1000) : Number(m[1].replace(',', '.'));
  }
  const turbo = t.match(/(?:turbo|boost)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*(ghz|mhz)/i);
  if (turbo) specs.frequenciaTurboMhz = turbo[2].toLowerCase() === 'ghz' ? Math.round(Number(turbo[1].replace(',', '.')) * 1000) : Number(turbo[1].replace(',', '.'));
  const l2 = primeiroMatch(t, /(?:cache\s*l2|L2)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mb/i, numeroPt);
  if (l2) specs.cacheL2Mb = l2;
  const l3 = primeiroMatch(t, /(?:cache\s*l3|L3)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mb/i, numeroPt);
  if (l3) specs.cacheL3Mb = l3;
  const tdp = primeiroMatch(t, /(?:tdp|pot[eê]ncia tdp)[^\d]{0,20}(\d+)\s*w/i, Number);
  if (tdp) specs.tdpWatts = tdp;
  const mem = normalizarTipoMemoria(extrairValorRotulado(t, ['Tipo de memória', 'Tipos de memória', 'Memória suportada']) || t);
  if (mem.length) specs.tiposMemoriaSuportados = mem;
  const freqMem = primeiroMatch(t, /(?:mem[oó]ria[^\d]{0,30}|memory[^\d]{0,30})(\d{3,5})\s*mhz/i, Number);
  if (freqMem) specs.frequenciaMemoriaMaximaMhz = freqMem;
  const capMem = primeiroMatch(t, /(?:mem[oó]ria[^\d]{0,30})(\d+)\s*gb/i, Number);
  if (capMem) specs.capacidadeMemoriaMaximaGb = capMem;
  const canais = primeiroMatch(t, /(?:canais|channels)[^\d]{0,15}(\d+)/i, Number);
  if (canais) specs.canaisMemoria = canais;
  const ecc = booleanoPresenca(t, /\bECC\b/i, /sem\s+ECC/i);
  if (ecc !== undefined) specs.suportaEcc = ecc;
  const pcie = primeiroMatch(t, /PCIe\s*(\d(?:\.\d)?)/i, (v) => v);
  if (pcie) specs.versaoPcie = pcie;
  const lanes = primeiroMatch(t, /PCIe[^\n]{0,40}x(\d+)/i, Number);
  if (lanes) specs.lanesPcie = lanes;
  const video = booleanoPresenca(t, /gr[aá]ficos?|v[ií]deo integrado|radeon graphics|uhd graphics|vega graphics/i, /sem\s+v[ií]deo\s+integrado|n[aã]o\s+possui\s+gr[aá]ficos/i);
  if (video !== undefined) specs.possuiVideoIntegrado = video;
  const cooler = booleanoPresenca(t, /cooler\s+(?:incluso|box)|acompanha\s+cooler/i, /sem\s+cooler/i);
  if (cooler !== undefined) specs.coolerIncluso = cooler;
  const unlocked = booleanoPresenca(t, /multiplicador\s+desbloqueado|unlocked/i, /bloqueado|locked/i);
  if (unlocked !== undefined) specs.multiplicadorDesbloqueado = unlocked;
  const oc = booleanoPresenca(t, /overclock|overclocking/i, /n[aã]o\s+suporta\s+overclock/i);
  if (oc !== undefined) specs.suporteOverclock = oc;
  return specs;
}

function extrairPlacaVideo(texto) {
  const t = String(texto || '');
  const specs = {};
  for (const [campo, rotulos] of [
    ['chipset', ['Chipset']],
    ['gpu', ['GPU', 'Processador gráfico', 'Processador grafico']],
    ['arquitetura', ['Arquitetura']],
    ['tipoMemoriaVideo', ['Tipo de memória', 'Tipo de memoria', 'Memória de vídeo', 'Memoria de video']],
  ]) {
    const valor = extrairValorRotulado(t, rotulos);
    if (valor) specs[campo] = valor;
  }
  const vram = primeiroMatch(t, /(?:mem[oó]ria de v[ií]deo|vram|mem[oó]ria)[^\d]{0,30}(\d+)\s*gb/i, Number);
  if (vram) specs.memoriaVideoGb = vram;
  const barramento = primeiroMatch(t, /(?:barramento|bus)[^\d]{0,20}(\d+)\s*bits?/i, Number);
  if (barramento) specs.barramentoBits = barramento;
  const base = primeiroMatch(t, /(?:clock base|base clock)[^\d]{0,20}(\d+)\s*mhz/i, Number);
  if (base) specs.clockBaseMhz = base;
  const boost = primeiroMatch(t, /(?:clock boost|boost clock|boost)[^\d]{0,20}(\d+)\s*mhz/i, Number);
  if (boost) specs.clockBoostMhz = boost;
  const gen = primeiroMatch(t, /PCIe\s*(?:Gen(?:era[cç][aã]o)?\s*)?(\d)/i, Number);
  if (gen) specs.geracaoPcie = gen;
  const largura = primeiroMatch(t, /PCIe[^\n]{0,30}x(\d+)/i, Number);
  if (largura) specs.larguraPcie = largura;
  const comprimento = primeiroMatch(t, /(?:comprimento|length)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (comprimento) specs.comprimentoMm = comprimento;
  const altura = primeiroMatch(t, /(?:altura|height)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (altura) specs.alturaMm = altura;
  const espessura = primeiroMatch(t, /(?:espessura|thickness)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (espessura) specs.espessuraMm = espessura;
  const slots = primeiroMatch(t, /(?:slots? ocupados|slot)[^\d]{0,20}(\d+(?:[.,]\d+)?)/i, numeroPt);
  if (slots) specs.slotsOcupados = slots;
  const consumo = primeiroMatch(t, /(?:consumo|power consumption|tdp)[^\d]{0,20}(\d+)\s*w/i, Number);
  if (consumo) specs.consumoWatts = consumo;
  const fonte = primeiroMatch(t, /(?:fonte recomendada|recommended PSU)[^\d]{0,20}(\d+)\s*w/i, Number);
  if (fonte) specs.potenciaFonteRecomendadaWatts = fonte;
  const pcie6 = primeiroMatch(t, /(?:PCIe|PCI-E)\s*6\s*pinos[^\d]{0,10}(\d+)/i, Number);
  if (pcie6 !== undefined) specs.conectoresPcie6Pinos = pcie6;
  const pcie8 = primeiroMatch(t, /(?:PCIe|PCI-E)\s*8\s*pinos[^\d]{0,10}(\d+)/i, Number);
  if (pcie8 !== undefined) specs.conectoresPcie8Pinos = pcie8;
  const h12 = primeiroMatch(t, /12VHPWR[^\d]{0,10}(\d+)/i, Number);
  if (h12 !== undefined) specs.conectores12vhpwr = h12;
  const h2x6 = primeiroMatch(t, /12V-2x6|12V2x6[^\d]{0,10}(\d+)/i, Number);
  if (h2x6 !== undefined) specs.conectores12v2x6 = h2x6;
  const hdmi = primeiroMatch(t, /HDMI[^\d]{0,10}(\d+)\s*(?:x|un|unidades|portas?)?/i, Number);
  if (hdmi !== undefined) specs.hdmi = hdmi;
  const dp = primeiroMatch(t, /DisplayPort[^\d]{0,10}(\d+)\s*(?:x|un|unidades|portas?)?/i, Number);
  if (dp !== undefined) specs.displayPort = dp;
  return specs;
}

function extrairPlacaMae(texto) {
  const t = String(texto || '');
  const specs = {};
  const socket = extrairSocket(t);
  if (socket) specs.socket = socket;
  const chipset = extrairValorRotulado(t, ['Chipset']);
  if (chipset) specs.chipset = chipset;
  const formato = normalizarFormatoPlacaMae(extrairValorRotulado(t, ['Formato', 'Form Factor', 'Fator de forma']) || primeiroMatch(t, /\b(E-ATX|EATX|ATX|Micro[- ]?ATX|mATX|Mini[- ]?ITX|MiniITX)\b/i));
  if (formato) specs.formato = formato;
  const tipos = normalizarTipoMemoria(extrairValorRotulado(t, ['Tipo de memória', 'Tipos de memória', 'Memória suportada']) || t);
  if (tipos.length) specs.tiposMemoriaSuportados = tipos;
  const formatosMem = [];
  if (/SO[- ]?DIMM/i.test(t)) formatosMem.push('SO_DIMM');
  if (/\bDIMM\b/i.test(t)) formatosMem.push('DIMM');
  if (formatosMem.length) specs.formatosMemoriaSuportados = [...new Set(formatosMem)];
  const jedec = [...new Set((t.match(/\b\d{3,5}\s*MHz\b/gi) || []).map((v) => Number(v.replace(/\D/g, ''))).filter((v) => v > 100 && v < 10000))];
  const oc = primeiroMatch(t, /(?:OC|overclock|overclocking)[^\d]{0,20}(\d{3,5})\s*mhz/i, Number);
  if (jedec.length) specs.frequenciasMemoriaJedecMhz = oc ? jedec.filter((v) => v < oc) : jedec.slice(0, 8);
  if (oc) specs.frequenciasMemoriaOverclockMhz = [oc];
  const slots = primeiroMatch(t, /(?:slots? de mem[oó]ria|slots? DIMM|slots? RAM)[^\d]{0,20}(\d+)/i, Number);
  if (slots) specs.slotsMemoria = slots;
  const maxMem = primeiroMatch(t, /(?:mem[oó]ria m[aá]xima|maximum memory)[^\d]{0,20}(\d+)\s*gb/i, Number);
  if (maxMem) specs.capacidadeMaximaMemoriaGb = maxMem;
  const maxSlot = primeiroMatch(t, /(?:por slot|per slot)[^\d]{0,20}(\d+)\s*gb/i, Number);
  if (maxSlot) specs.capacidadeMaximaPorSlotGb = maxSlot;
  const xmp = booleanoPresenca(t, /\bXMP\b/i, /sem\s+XMP/i);
  if (xmp !== undefined) specs.suportaXmp = xmp;
  const expo = booleanoPresenca(t, /\bEXPO\b/i, /sem\s+EXPO/i);
  if (expo !== undefined) specs.suportaExpo = expo;
  const ecc = booleanoPresenca(t, /\bECC\b/i, /sem\s+ECC/i);
  if (ecc !== undefined) specs.suportaEcc = ecc;
  const registered = booleanoPresenca(t, /mem[oó]ria registrada|registered memory/i, /sem\s+mem[oó]ria registrada/i);
  if (registered !== undefined) specs.suportaMemoriaRegistrada = registered;
  const saidas = [];
  for (const nome of ['HDMI', 'DisplayPort', 'VGA', 'DVI', 'USB-C']) if (new RegExp(`\\b${nome.replace('-', '[- ]?')}\\b`, 'i').test(t)) saidas.push(nome);
  if (saidas.length) specs.saidasVideo = [...new Set(saidas)];
  const sata = primeiroMatch(t, /(?:portas?|conectores?)\s*SATA[^\d]{0,10}(\d+)/i, Number) || primeiroMatch(t, /SATA[^\d]{0,10}(\d+)\s*(?:portas?|x)/i, Number);
  if (sata) specs.portasSata = sata;
  const pcie = primeiroMatch(t, /PCIe\s*(\d(?:\.\d)?)/i, (v) => v);
  if (pcie) specs.versaoPcie = pcie;
  const wifi = booleanoPresenca(t, /\bWi[- ]?Fi\b/i, /sem\s+Wi[- ]?Fi/i);
  if (wifi !== undefined) specs.wifi = wifi;
  const bt = booleanoPresenca(t, /\bBluetooth\b/i, /sem\s+Bluetooth/i);
  if (bt !== undefined) specs.bluetooth = bt;
  const ethernet = extrairValorRotulado(t, ['Ethernet', 'Rede']);
  if (ethernet) specs.ethernet = ethernet;
  const flash = booleanoPresenca(t, /BIOS Flashback|Flashback/i, /sem\s+BIOS Flashback/i);
  if (flash !== undefined) specs.biosFlashback = flash;
  return specs;
}

function extrairGabinete(texto) {
  const t = String(texto || '');
  const specs = {};
  const tamanhoTexto = extrairValorRotulado(t, ['Tamanho', 'Tipo', 'Form Factor']) || '';
  const tamanhoFonte = `${tamanhoTexto} ${t}`;
  if (/full[- ]?tower/i.test(tamanhoFonte)) specs.tamanho = 'FULL_TOWER';
  else if (/mid[- ]?tower/i.test(tamanhoFonte)) specs.tamanho = 'MID_TOWER';
  else if (/mini[- ]?tower/i.test(tamanhoFonte)) specs.tamanho = 'MINI_TOWER';
  else if (/\bSFF\b|small form factor/i.test(tamanhoFonte)) specs.tamanho = 'SFF';
  else if (/open[- ]?frame/i.test(tamanhoFonte)) specs.tamanho = 'OPEN_FRAME';
  const dim = (campo, rotulos) => {
    const valor = primeiroMatch(t, new RegExp(`(?:${rotulos.join('|')})[^\\d]{0,20}(\\d+(?:[.,]\\d+)?)\\s*mm`, 'i'), numeroPt);
    if (valor) specs[campo] = valor;
  };
  dim('alturaMm', ['altura', 'height']);
  dim('larguraMm', ['largura', 'width']);
  dim('profundidadeMm', ['profundidade', 'depth']);
  const mobo = [];
  for (const [regex, val] of [[/E-ATX|EATX/i, 'E_ATX'], [/Micro[- ]?ATX|mATX/i, 'MICRO_ATX'], [/Mini[- ]?ITX|MiniITX/i, 'MINI_ITX'], [/\bATX\b/i, 'ATX']]) if (regex.test(t)) mobo.push(val);
  if (mobo.length) specs.formatosPlacaMaeSuportados = [...new Set(mobo)];
  const fontes = [];
  for (const [regex, val] of [[/SFX-L/i, 'SFX_L'], [/SFX/i, 'SFX'], [/TFX/i, 'TFX'], [/FLEX[- ]?ATX/i, 'FLEX_ATX'], [/\bATX\b/i, 'ATX']]) if (regex.test(t)) fontes.push(val);
  if (fontes.length) specs.formatosFonteSuportados = [...new Set(fontes)];
  const campoMm = [
    ['comprimentoMaximoFonteMm', /(?:fonte[^\d]{0,30}(?:comprimento|length)|comprimento\s+m[aá]ximo\s+da\s+fonte)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i],
    ['comprimentoMaximoGpuMm', /(?:gpu|placa de v[ií]deo)[^\d]{0,30}(?:comprimento|length|m[aá]ximo)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i],
    ['alturaMaximaGpuMm', /(?:altura\s+m[aá]xima\s+(?:da\s+)?gpu|altura\s+m[aá]xima\s+placa)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i],
    ['alturaMaximaCoolerCpuMm', /(?:altura\s+m[aá]xima\s+(?:do\s+)?cooler|cpu\s+cooler)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i],
    ['espacoGerenciamentoCabosMm', /(?:gerenciamento|gest[aã]o)\s+(?:de\s+)?cabos[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i],
  ];
  for (const [campo, regex] of campoMm) {
    const valor = primeiroMatch(t, regex, numeroPt);
    if (valor) specs[campo] = valor;
  }
  const slots = primeiroMatch(t, /(?:slots? traseiros|expansion slots)[^\d]{0,20}(\d+)/i, Number);
  if (slots) specs.slotsTraseiros = slots;
  const baias25 = primeiroMatch(t, /(?:2[.,]?5["' ]?\s*(?:baias?|bays?))[^\d]{0,10}(\d+)/i, Number);
  if (baias25 !== undefined) specs.baias25 = baias25;
  const baias35 = primeiroMatch(t, /(?:3[.,]?5["' ]?\s*(?:baias?|bays?))[^\d]{0,10}(\d+)/i, Number);
  if (baias35 !== undefined) specs.baias35 = baias35;
  const vertical = booleanoPresenca(t, /GPU\s+vertical|placa\s+de\s+v[ií]deo\s+vertical/i, /sem\s+suporte\s+(?:a\s+)?GPU\s+vertical/i);
  if (vertical !== undefined) specs.suportaGpuVertical = vertical;
  return specs;
}

function extrairCooler(texto) {
  const t = String(texto || '');
  const specs = {};
  if (/water\s*cooler|liquid\s+cooling|refrigera[cç][aã]o\s+l[ií]quida/i.test(t)) specs.tipo = 'WATER_COOLER';
  else if (/air\s*cooler|cooler\s+a\s+ar|refrigera[cç][aã]o\s+a\s+ar/i.test(t)) specs.tipo = 'AIR_COOLER';
  const sockets = [...new Set((t.match(/\b(AM[345]|LGA\s*\d{3,5}|TR4|sTRX4|sTR5)\b/gi) || []).map((v) => v.replace(/\s+/g, '').toUpperCase()))];
  if (sockets.length) specs.socketsSuportados = sockets;
  const tdp = primeiroMatch(t, /(?:capacidade t[eé]rmica|thermal design|tdp)[^\d]{0,30}(\d+)\s*w/i, Number);
  if (tdp) specs.capacidadeTermicaWatts = tdp;
  const altura = primeiroMatch(t, /(?:altura|height)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (altura) specs.alturaMm = altura;
  const largura = primeiroMatch(t, /(?:largura|width)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (largura) specs.larguraMm = largura;
  const profundidade = primeiroMatch(t, /(?:profundidade|depth)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (profundidade) specs.profundidadeMm = profundidade;
  const radiador = primeiroMatch(t, /(?:radiador|radiator)[^\d]{0,20}(120|140|240|280|360|420)\s*mm/i, Number);
  if (radiador) specs.tamanhoRadiadorMm = radiador;
  const fans = primeiroMatch(t, /(?:quantidade de ventoinhas|fans?)[^\d]{0,20}(\d+)/i, Number);
  if (fans) specs.quantidadeVentoinhas = fans;
  const fanSize = primeiroMatch(t, /(?:ventoinha|fan)[^\d]{0,20}(120|140|92|80)\s*mm/i, Number);
  if (fanSize) specs.tamanhoVentoinhaMm = fanSize;
  const rpm = primeiroMatch(t, /(?:velocidade|rpm)[^\d]{0,20}(\d{3,5})\s*rpm/i, Number);
  if (rpm) specs.velocidadeMaxRpm = rpm;
  const ruido = primeiroMatch(t, /(?:ru[ií]do|noise)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*dba?/i, numeroPt);
  if (ruido) specs.ruidoDb = ruido;
  const vida = primeiroMatch(t, /(?:vida u?til|lifetime)[^\d]{0,20}(\d[\d.,]*)\s*(?:h|horas|hours)/i, (v) => Number(String(v).replace(/[.,]/g, '')));
  if (vida) specs.vidaUtilHoras = vida;
  const peso = primeiroMatch(t, /(?:peso|weight)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*g/i, numeroPt);
  if (peso) specs.pesoGramas = peso;
  const rgb = booleanoPresenca(t, /\brgb\b/i, /sem\s+rgb/i);
  if (rgb !== undefined) specs.rgb = rgb;
  const argb = booleanoPresenca(t, /\bar\?gb\b|\bargb\b/i, /sem\s+argb/i);
  if (argb !== undefined) specs.argb = argb;
  return specs;
}

function extrairVentoinha(texto) {
  const t = String(texto || '');
  const specs = {};
  const tamanho = primeiroMatch(t, /(?:tamanho|size)[^\d]{0,20}(\d{2,3})\s*mm/i, Number) || primeiroMatch(t, /\b(80|92|120|140|200)\s*mm\b/i, Number);
  if (tamanho) specs.tamanhoMm = tamanho;
  const esp = primeiroMatch(t, /(?:espessura|thickness)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (esp) specs.espessuraMm = esp;
  const rpm = [...(t.match(/(\d{3,5})\s*rpm/gi) || [])].map((v) => Number(v.replace(/\D/g, '')));
  if (rpm.length === 1) specs.rpmMaxima = rpm[0];
  if (rpm.length >= 2) {
    specs.rpmMinima = Math.min(...rpm);
    specs.rpmMaxima = Math.max(...rpm);
  }
  const fluxo = primeiroMatch(t, /(?:fluxo de ar|airflow)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*cfm/i, numeroPt);
  if (fluxo) specs.fluxoArCfm = fluxo;
  const pressao = primeiroMatch(t, /(?:press[aã]o est[aá]tica|static pressure)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mmh2o/i, numeroPt);
  if (pressao) specs.pressaoEstaticaMmH2o = pressao;
  const ruido = primeiroMatch(t, /(?:ru[ií]do|noise)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*dba?/i, numeroPt);
  if (ruido) specs.ruidoDb = ruido;
  if (/PWM|4[- ]?pinos|4[- ]?pin/i.test(t)) specs.conector = 'PWM_4_PINOS';
  else if (/3[- ]?pinos|3[- ]?pin|DC/i.test(t)) specs.conector = 'DC_3_PINOS';
  else if (/Molex/i.test(t)) specs.conector = 'MOLEX';
  const volts = primeiroMatch(t, /(?:tens[aã]o|voltagem)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*v/i, numeroPt);
  if (volts) specs.tensaoVolts = volts;
  const amp = primeiroMatch(t, /(?:corrente|current)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*a/i, numeroPt);
  if (amp) specs.correnteAmperes = amp;
  const pwm = booleanoPresenca(t, /\bPWM\b/i, /sem\s+PWM/i);
  if (pwm !== undefined) specs.pwm = pwm;
  const rgb = booleanoPresenca(t, /\brgb\b/i, /sem\s+rgb/i);
  if (rgb !== undefined) specs.rgb = rgb;
  const argb = booleanoPresenca(t, /\bARGB\b/i, /sem\s+ARGB/i);
  if (argb !== undefined) specs.argb = argb;
  const reverso = booleanoPresenca(t, /fluxo\s+reverso|reverse\s+flow/i, /fluxo\s+normal/i);
  if (reverso !== undefined) specs.fluxoReverso = reverso;
  return specs;
}


function extrairFone(texto) {
  const t = String(texto || '');
  const specs = {};
  const tipoConexao = extrairValorRotulado(t, ['Tipo de conexão', 'Tipo de conexao', 'Conexão', 'Conexao', 'Conectividade']);
  if (tipoConexao) specs.tipoConexao = tipoConexao;
  const wireless = booleanoPresenca(t, /\bwireless\b|\bsem\s+fio\b|\b2\.4\s*ghz\b/i, /\bsomente\s+cabo\b/i);
  if (wireless !== undefined) specs.wireless = wireless;
  const bluetooth = booleanoPresenca(t, /\bbluetooth\b/i, /\bsem\s+bluetooth\b/i);
  if (bluetooth !== undefined) specs.bluetooth = bluetooth;
  const driver = primeiroMatch(t, /(?:driver|diafragma)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*mm/i, numeroPt);
  if (driver) specs.driverMm = driver;
  const microfone = booleanoPresenca(t, /\bmicrofone\b|\bmicrophone\b/i, /sem\s+microfone|n[aã]o\s+possui\s+microfone/i);
  if (microfone !== undefined) specs.microfone = microfone;
  const surround = booleanoPresenca(t, /surround|7\.1|5\.1/i, /sem\s+surround/i);
  if (surround !== undefined) specs.somSurround = surround;
  const impedancia = primeiroMatch(t, /(?:imped[aâ]ncia|impedance)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*ohms?/i, numeroPt);
  if (impedancia) specs.impedancia = impedancia;
  const peso = primeiroMatch(t, /(?:peso|weight)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*g/i, numeroPt);
  if (peso) specs.pesoGramas = peso;
  const bateria = primeiroMatch(t, /(?:bateria|autonomia|battery)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*(?:h|horas|hours)/i, numeroPt);
  if (bateria) specs.bateriaHoras = bateria;
  return specs;
}

function extrairNotebook(texto) {
  const t = String(texto || '');
  const specs = {};
  const processador = extrairValorRotulado(t, ['Processador', 'CPU']);
  if (processador) specs.processadorNome = processador;
  const gpu = extrairValorRotulado(t, ['GPU', 'Placa de vídeo', 'Placa de video']);
  if (gpu) specs.gpuNome = gpu;
  const cores = primeiroMatch(t, /(?:n[uú]cleos|cores)[^\d]{0,15}(\d+)/i, Number);
  if (cores) specs.nucleos = cores;
  const threads = primeiroMatch(t, /threads?[^\d]{0,15}(\d+)/i, Number);
  if (threads) specs.threads = threads;
  const ram = primeiroMatch(t, /(?:RAM|mem[oó]ria)[^\d]{0,20}(\d+)\s*GB/i, Number);
  if (ram) specs.ramInstaladaGb = ram;
  const tipoRam = primeiroMatch(t, /\b(DDR3|DDR4|DDR5)\b/i, (v) => v.toUpperCase());
  if (tipoRam) specs.tipoMemoria = tipoRam;
  const mhz = primeiroMatch(t, /(?:RAM|mem[oó]ria)[^\d]{0,30}(\d{3,5})\s*MHz/i, Number);
  if (mhz) specs.frequenciaMhz = mhz;
  const armazenamento = primeiroMatch(t, /(?:SSD|armazenamento|storage)[^\d]{0,30}(\d+)\s*(GB|TB)/i, (v) => v);
  if (armazenamento) {
    const m = t.match(/(?:SSD|armazenamento|storage)[^\d]{0,30}(\d+)\s*(GB|TB)/i);
    specs.armazenamentoGb = m?.[2].toUpperCase() === 'TB' ? Number(m[1]) * 1000 : Number(m[1]);
  }
  const tela = primeiroMatch(t, /(\d+(?:[.,]\d+)?)\s*(?:"|polegadas)/i, numeroPt);
  if (tela) specs.tamanhoTelaPolegadas = tela;
  const resolucao = primeiroMatch(t, /(\d{3,4})\s*[x×]\s*(\d{3,4})/i, (v) => v);
  const rm = t.match(/(\d{3,4})\s*[x×]\s*(\d{3,4})/i);
  if (rm) {
    specs.resolucaoLargura = Number(rm[1]);
    specs.resolucaoAltura = Number(rm[2]);
  }
  const hz = primeiroMatch(t, /(\d{2,4})\s*hz/i, Number);
  if (hz) specs.taxaAtualizacaoHz = hz;
  const painel = primeiroMatch(t, /\b(IPS|VA|TN|OLED|Mini[- ]?LED)\b/i, (v) => v.toUpperCase());
  if (painel) specs.tipoPainel = painel;
  const brilho = primeiroMatch(t, /(\d+)\s*nits?/i, Number);
  if (brilho) specs.brilhoNits = brilho;
  const touch = booleanoPresenca(t, /\btouch(?:screen)?\b|tela\s+touch/i, /sem\s+touch/i);
  if (touch !== undefined) specs.touch = touch;
  const peso = primeiroMatch(t, /(?:peso|weight)[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*kg/i, numeroPt);
  if (peso) specs.pesoKg = peso;
  const wifi = extrairValorRotulado(t, ['Wi-Fi', 'Wifi']);
  if (wifi) specs.wifi = wifi;
  const bt = extrairValorRotulado(t, ['Bluetooth']);
  if (bt) specs.bluetooth = bt;
  const so = extrairValorRotulado(t, ['Sistema Operacional', 'Sistema operacional', 'SO']);
  if (so) specs.sistemaOperacional = so;
  const webcam = booleanoPresenca(t, /\bwebcam\b|c[aâ]mera/i, /sem\s+webcam|sem\s+c[aâ]mera/i);
  if (webcam !== undefined) specs.webcam = webcam;
  const numerico = [
    ['usbA', /(?:USB-A|USB A)[^\d]{0,10}(\d+)/i],
    ['usbC', /(?:USB-C|USB C)[^\d]{0,10}(\d+)/i],
    ['thunderbolt', /Thunderbolt[^\d]{0,10}(\d+)/i],
    ['hdmi', /HDMI[^\d]{0,10}(\d+)/i],
    ['displayPort', /DisplayPort[^\d]{0,10}(\d+)/i],
  ];
  for (const [campo, regex] of numerico) {
    const valor = primeiroMatch(t, regex, Number);
    if (valor !== undefined) specs[campo] = valor;
  }
  const ethernet = booleanoPresenca(t, /\bEthernet\b|RJ45/i, /sem\s+ethernet/i);
  if (ethernet !== undefined) specs.ethernet = ethernet;
  const leitor = booleanoPresenca(t, /leitor\s+de\s+cart[aã]o|card\s+reader/i, /sem\s+leitor\s+de\s+cart[aã]o/i);
  if (leitor !== undefined) specs.leitorCartao = leitor;
  return specs;
}

function extrairPorCategoria(categoria, texto) {
  let specs = {};
  switch (categoria) {
    case 'TECLADO': specs = extrairTeclado(texto); break;
    case 'MOUSE': specs = extrairMouse(texto); break;
    case 'MONITOR': specs = extrairMonitor(texto); break;
    case 'MEMORIA_RAM': specs = extrairMemoriaRam(texto); break;
    case 'ARMAZENAMENTO': specs = extrairArmazenamento(texto); break;
    case 'FONTE': specs = extrairFonte(texto); break;
    case 'PROCESSADOR': specs = extrairProcessador(texto); break;
    case 'PLACA_VIDEO': specs = extrairPlacaVideo(texto); break;
    case 'PLACA_MAE': specs = extrairPlacaMae(texto); break;
    case 'GABINETE': specs = extrairGabinete(texto); break;
    case 'COOLER': specs = extrairCooler(texto); break;
    case 'VENTOINHA': specs = extrairVentoinha(texto); break;
    case 'FONE': specs = extrairFone(texto); break;
    case 'NOTEBOOK': specs = extrairNotebook(texto); break;
    default: specs = {};
  }

  const schema = SCHEMAS[categoria];
  if (!schema) return {};
  return Object.fromEntries(
    Object.entries(specs).filter(([chave, valor]) => schema.campos.includes(chave) && valor !== undefined && valor !== null && valor !== '')
  );
}

module.exports = { extrairPorCategoria };
