const { SCHEMAS } = require('./backend-schemas');

function primeiroMatch(texto, regex, transform = (v) => v) {
  const m = String(texto || '').match(regex);
  return m?.[1] != null ? transform(m[1]) : undefined;
}

function numeroPt(v) {
  const n = Number(String(v).replace(',', '.'));
  return Number.isFinite(n) ? n : undefined;
}

function booleanoPresenca(texto, positivo, negativo) {
  const fonte = String(texto || '');
  if (negativo && negativo.test(fonte)) return false;
  if (positivo.test(fonte)) return true;
  return undefined;
}

function extrairTeclado(texto) {
  const t = String(texto || '');
  const specs = {};

  if (/teclado\s+mec[aâ]nico|mec[aâ]nico/i.test(t)) specs.tipo = 'Mecânico';
  else if (/membrana/i.test(t)) specs.tipo = 'Membrana';

  const sw = primeiroMatch(t, /(?:switch(?:es)?)[\s:\-]*((?:outemu|cherry\s*mx|gateron|kailh|huano|akko)?\s*(?:brown|red|blue|black|yellow|silver|green|roxo|rosa))/i, v => v.trim());
  if (sw) specs.switch = sw;

  if (/abnt\s*2|abnt2/i.test(t)) specs.abnt2 = true;

  if (/\b60%\b/i.test(t)) specs.tamanho = '60%';
  else if (/\b65%\b/i.test(t)) specs.tamanho = '65%';
  else if (/\b75%\b/i.test(t)) specs.tamanho = '75%';
  else if (/\b80%\b|\btenkeyless\b|\btkl\b/i.test(t)) specs.tamanho = 'TKL';
  else if (/\b100%\b|full[- ]?size/i.test(t)) specs.tamanho = 'Full Size';

  const layout = primeiroMatch(t, /(?:layout)[\s:\-]*([A-Za-z0-9\- ]{2,30})/i, v => v.trim());
  if (layout) specs.layout = layout;

  const rgb = booleanoPresenca(t, /\brgb\b/i, /sem\s+rgb/i);
  if (rgb !== undefined) specs.rgb = rgb;

  const hotSwap = booleanoPresenca(t, /hot\s*[- ]?swap|hotswap/i, /n[aã]o\s+(?:possui\s+)?hot\s*[- ]?swap/i);
  if (hotSwap !== undefined) specs.hotSwap = hotSwap;

  const bluetooth = booleanoPresenca(t, /bluetooth/i, /sem\s+bluetooth/i);
  if (bluetooth !== undefined) specs.bluetooth = bluetooth;

  const wireless = booleanoPresenca(t, /wireless|sem\s+fio|2\.4\s*ghz/i, /com\s+fio\s+apenas|somente\s+cabo/i);
  if (wireless !== undefined) specs.wireless = wireless;

  const usb = booleanoPresenca(t, /usb(?:-c|\s*tipo\s*c)?/i, /sem\s+usb/i);
  if (usb !== undefined) specs.usb = usb;

  if (/usb[- ]?c|tipo\s*c/i.test(t)) specs.conexao = 'USB-C';
  else if (/usb/i.test(t)) specs.conexao = 'USB';
  else if (/bluetooth/i.test(t)) specs.conexao = 'Bluetooth';

  return specs;
}

function extrairMouse(texto) {
  const t = String(texto || '');
  const specs = {};
  const dpi = primeiroMatch(t, /([\d.]+)\s*dpi/i, v => Number(v.replace(/\./g, '')));
  if (dpi) specs.dpiMaximo = dpi;
  const polling = primeiroMatch(t, /(\d+)\s*hz/i, Number);
  if (polling) specs.pollingRateHz = polling;
  const botoes = primeiroMatch(t, /(\d+)\s*bot[oõ]es/i, Number);
  if (botoes) specs.botoes = botoes;
  const peso = primeiroMatch(t, /(\d+(?:[.,]\d+)?)\s*g(?:ramas)?\b/i, numeroPt);
  if (peso) specs.pesoGramas = peso;
  if (/bluetooth/i.test(t)) specs.bluetooth = true;
  if (/wireless|sem\s+fio|2\.4\s*ghz/i.test(t)) specs.wireless = true;
  if (/\brgb\b/i.test(t)) specs.rgb = true;
  return specs;
}

function extrairMonitor(texto) {
  const t = String(texto || '');
  const specs = {};
  const polegadas = primeiroMatch(t, /(\d+(?:[.,]\d+)?)\s*(?:"|polegadas)/i, numeroPt);
  if (polegadas) specs.tamanhoPolegadas = polegadas;
  const resolucao = primeiroMatch(t, /(\d{3,4}\s*[x×]\s*\d{3,4})/i, v => v.replace(/\s+/g, '').replace('×','x'));
  if (resolucao) specs.resolucao = resolucao;
  const hz = primeiroMatch(t, /(\d{2,4})\s*hz/i, Number);
  if (hz) specs.taxaAtualizacaoHz = hz;
  const ms = primeiroMatch(t, /(\d+(?:[.,]\d+)?)\s*ms/i, numeroPt);
  if (ms) specs.tempoRespostaMs = ms;
  const nits = primeiroMatch(t, /(\d+)\s*nits?/i, Number);
  if (nits) specs.brilhoNits = nits;
  if (/\bhdr\b/i.test(t)) specs.hdr = true;
  if (/free\s*sync|freesync/i.test(t)) specs.freeSync = true;
  if (/g\s*[- ]?sync/i.test(t)) specs.gSync = true;
  if (/adaptive\s*sync/i.test(t)) specs.adaptiveSync = true;
  const painel = primeiroMatch(t, /\b(ips|va|tn|oled|mini[- ]?led)\b/i, v => v.toUpperCase());
  if (painel) specs.tipoPainel = painel;
  return specs;
}

function extrairMemoriaRam(texto) {
  const t = String(texto || '');
  const specs = {};
  const tipo = primeiroMatch(t, /\b(DDR3|DDR4|DDR5)\b/i, v => v.toUpperCase());
  if (tipo) specs.tipo = tipo;
  specs.formato = /so[- ]?dimm/i.test(t) ? 'SO_DIMM' : /\bdimm\b/i.test(t) ? 'DIMM' : undefined;
  const total = primeiroMatch(t, /(\d+)\s*gb/i, Number);
  const kit = primeiroMatch(t, /(?:kit\s*)?(\d+)\s*[xX]\s*(\d+)\s*gb/i, null);
  const kitMatch = t.match(/(?:kit\s*)?(\d+)\s*[xX]\s*(\d+)\s*gb/i);
  if (kitMatch) {
    specs.quantidadeModulos = Number(kitMatch[1]);
    specs.capacidadePorModuloGb = Number(kitMatch[2]);
  } else if (total) {
    specs.quantidadeModulos = 1;
    specs.capacidadePorModuloGb = total;
  }
  const mhz = primeiroMatch(t, /(\d{3,5})\s*mhz/i, Number);
  if (mhz) specs.frequenciaMhz = mhz;
  const cl = primeiroMatch(t, /\bCL\s*(\d{1,3})\b/i, Number);
  if (cl) specs.latenciaCl = cl;
  const volts = primeiroMatch(t, /(\d+(?:[.,]\d+)?)\s*v\b/i, numeroPt);
  if (volts) specs.tensaoVolts = volts;
  if (/\brgb\b/i.test(t)) specs.rgb = true;
  if (/\bxmp\b/i.test(t)) specs.suportaXmp = true;
  if (/\bexpo\b/i.test(t)) specs.suportaExpo = true;
  return specs;
}

function extrairArmazenamento(texto) {
  const t = String(texto || '');
  const specs = {};
  if (/\bssd\b/i.test(t)) specs.tipo = 'SSD';
  else if (/\bhdd\b|disco r[ií]gido/i.test(t)) specs.tipo = 'HDD';
  if (/m\.2/i.test(t)) specs.formato = 'M2';
  else if (/2[.,]5\s*(?:"|polegadas)/i.test(t)) specs.formato = 'POLEGADAS_2_5';
  else if (/3[.,]5\s*(?:"|polegadas)/i.test(t)) specs.formato = 'POLEGADAS_3_5';
  if (/nvme|pcie/i.test(t)) specs.interface = 'NVME_PCIE';
  else if (/\bsata\b/i.test(t)) specs.interface = 'SATA';
  const tb = primeiroMatch(t, /(\d+(?:[.,]\d+)?)\s*tb\b/i, numeroPt);
  const gb = primeiroMatch(t, /(\d+)\s*gb\b/i, Number);
  if (tb) specs.capacidadeGb = Math.round(tb * 1000);
  else if (gb) specs.capacidadeGb = gb;
  const leitura = primeiroMatch(t, /(?:leitura|read)[^\d]{0,30}(\d{3,6})\s*mb\/s/i, Number);
  if (leitura) specs.leituraSequencialMbps = leitura;
  const escrita = primeiroMatch(t, /(?:grava[cç][aã]o|escrita|write)[^\d]{0,30}(\d{3,6})\s*mb\/s/i, Number);
  if (escrita) specs.escritaSequencialMbps = escrita;
  return specs;
}

function extrairFonte(texto) {
  const t = String(texto || '');
  const specs = {};
  const watts = primeiroMatch(t, /(\d{3,5})\s*w(?:atts?)?\b/i, Number);
  if (watts) specs.potenciaWatts = watts;
  if (/\bSFX-L\b/i.test(t)) specs.formato = 'SFX_L';
  else if (/\bSFX\b/i.test(t)) specs.formato = 'SFX';
  else if (/\bATX\b/i.test(t)) specs.formato = 'ATX';
  const cert = primeiroMatch(t, /(80\s*plus\s*(?:white|bronze|silver|gold|platinum|titanium)?)/i, v => v.replace(/\s+/g,' ').trim());
  if (cert) specs.certificacao = cert;
  if (/semi[- ]?modular/i.test(t)) specs.modularidade = 'SEMI_MODULAR';
  else if (/n[aã]o[- ]?modular/i.test(t)) specs.modularidade = 'NAO_MODULAR';
  else if (/\bmodular\b/i.test(t)) specs.modularidade = 'MODULAR';
  return specs;
}

function extrairProcessador(texto) {
  const t = String(texto || '');
  const specs = {};
  const socket = primeiroMatch(t, /\b(AM[345]|LGA\s*\d{3,5}|TR4|sTRX4|sTR5)\b/i, v => v.replace(/\s+/g,'').toUpperCase());
  if (socket) specs.socket = socket;
  const cores = primeiroMatch(t, /(\d+)\s*n[uú]cleos?/i, Number);
  if (cores) specs.nucleos = cores;
  const threads = primeiroMatch(t, /(\d+)\s*threads?/i, Number);
  if (threads) specs.threads = threads;
  const tdp = primeiroMatch(t, /(?:tdp[^\d]{0,20})?(\d{2,4})\s*w(?:atts?)?\b/i, Number);
  if (tdp) specs.tdpWatts = tdp;
  const ddr = [...new Set((t.match(/\bDDR[345]\b/gi) || []).map(v => v.toUpperCase()))];
  if (ddr.length) specs.tiposMemoriaSuportados = ddr;
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
    default: specs = {};
  }

  const schema = SCHEMAS[categoria];
  if (!schema) return {};
  return Object.fromEntries(
    Object.entries(specs).filter(([chave, valor]) => schema.campos.includes(chave) && valor !== undefined)
  );
}

module.exports = { extrairPorCategoria };
