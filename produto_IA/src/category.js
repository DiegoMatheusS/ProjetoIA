const { SCHEMAS } = require('./backend-schemas');

const REGRAS = [
  ['NOTEBOOK', /\b(notebook|laptop|ultrabook)\b/i],
  ['PLACA_MAE', /\b(placa[- ]?m[aã]e|motherboard)\b/i],
  ['PLACA_VIDEO', /\b(placa de v[ií]deo|gpu|geforce|radeon|rtx\s?\d|rx\s?\d)\b/i],
  ['MEMORIA_RAM', /\b(mem[oó]ria ram|ddr[345]|dimm|sodimm|so-dimm)\b/i],
  ['ARMAZENAMENTO', /\b(ssd|nvme|hdd|disco r[ií]gido|m\.2)\b/i],
  ['FONTE', /\b(fonte(?: de alimenta[cç][aã]o)?|power supply|psu)\b/i],
  ['GABINETE', /\b(gabinete|case gamer|computer case)\b/i],
  ['COOLER', /\b(water cooler|air cooler|cooler (?:para|de) processador|cpu cooler)\b/i],
  ['VENTOINHA', /\b(ventoinha|fan gamer|case fan)\b/i],
  ['PROCESSADOR', /\b(processador|cpu|ryzen|core i[3579]|xeon)\b/i],
  ['MONITOR', /\bmonitor\b/i],
  ['TECLADO', /\bteclado\b/i],
  ['MOUSE', /\bmouse\b/i],
  ['FONE', /\b(headset|fone de ouvido|headphone)\b/i],
  ['MICROFONE', /\bmicrofone\b/i],
];

function detectarCategoria(texto, categoriaForcada) {
  if (categoriaForcada) {
    const cat = String(categoriaForcada).trim().toUpperCase();
    if (SCHEMAS[cat]) return cat;
  }

  const fonte = String(texto || '');
  for (const [categoria, regex] of REGRAS) {
    if (regex.test(fonte)) return categoria;
  }
  return null;
}

module.exports = { detectarCategoria };
