const SOURCES = [
  { id: 'KABUM', nome: 'KaBuM!', tipo: 'LOJA', prioridade: 1, dominios: ['kabum.com.br'] },
  { id: 'MAGALU', nome: 'Magazine Luiza', tipo: 'LOJA', prioridade: 1, dominios: ['magazineluiza.com.br', 'magazinevoce.com.br'] },
  { id: 'PICHAU', nome: 'Pichau', tipo: 'LOJA', prioridade: 1, dominios: ['pichau.com.br'] },
  { id: 'TERABYTE', nome: 'TerabyteShop', tipo: 'LOJA', prioridade: 1, dominios: ['terabyteshop.com.br'] },
  { id: 'AMAZON', nome: 'Amazon', tipo: 'LOJA', prioridade: 1, dominios: ['amazon.com.br', 'amazon.com'] },
  { id: 'DELL', nome: 'Dell', tipo: 'FABRICANTE', prioridade: 2, dominios: ['dell.com'] },
  { id: 'LENOVO', nome: 'Lenovo', tipo: 'FABRICANTE', prioridade: 2, dominios: ['lenovo.com'] },
  { id: 'ASUS', nome: 'ASUS', tipo: 'FABRICANTE', prioridade: 2, dominios: ['asus.com'] },
  { id: 'ACER', nome: 'Acer', tipo: 'FABRICANTE', prioridade: 2, dominios: ['acer.com'] },
  { id: 'GIGABYTE', nome: 'Gigabyte', tipo: 'FABRICANTE', prioridade: 2, dominios: ['gigabyte.com'] },
  { id: 'MSI', nome: 'MSI', tipo: 'FABRICANTE', prioridade: 2, dominios: ['msi.com'] },
  { id: 'CORSAIR', nome: 'Corsair', tipo: 'FABRICANTE', prioridade: 2, dominios: ['corsair.com'] },
  { id: 'KINGSTON', nome: 'Kingston', tipo: 'FABRICANTE', prioridade: 2, dominios: ['kingston.com'] },
  { id: 'LOGITECH', nome: 'Logitech', tipo: 'FABRICANTE', prioridade: 2, dominios: ['logitech.com'] },
  { id: 'HYPERX', nome: 'HyperX', tipo: 'FABRICANTE', prioridade: 2, dominios: ['hyperx.com'] },
  { id: 'AMD', nome: 'AMD', tipo: 'FABRICANTE', prioridade: 2, dominios: ['amd.com'] },
  { id: 'INTEL', nome: 'Intel', tipo: 'FABRICANTE', prioridade: 2, dominios: ['intel.com'] },
  { id: 'NVIDIA', nome: 'NVIDIA', tipo: 'FABRICANTE', prioridade: 2, dominios: ['nvidia.com'] },
  { id: 'SAMSUNG', nome: 'Samsung', tipo: 'FABRICANTE', prioridade: 2, dominios: ['samsung.com'] },
  { id: 'WESTERN_DIGITAL', nome: 'Western Digital', tipo: 'FABRICANTE', prioridade: 2, dominios: ['westerndigital.com'] },
  { id: 'SEAGATE', nome: 'Seagate', tipo: 'FABRICANTE', prioridade: 2, dominios: ['seagate.com'] },
  { id: 'THERMALTAKE', nome: 'Thermaltake', tipo: 'FABRICANTE', prioridade: 2, dominios: ['thermaltake.com'] },
  { id: 'COUGAR', nome: 'Cougar', tipo: 'FABRICANTE', prioridade: 2, dominios: ['cougargaming.com'] },
  { id: 'REDRAGON', nome: 'Redragon', tipo: 'FABRICANTE', prioridade: 2, dominios: ['redragonshop.com'] },
  { id: 'MERCADO_LIVRE', nome: 'Mercado Livre', tipo: 'MARKETPLACE', prioridade: 9, bloqueado: true, dominios: ['mercadolivre.com.br', 'mercadolibre.com'] },
];

function identificarFonte(url) {
  let host = '';
  try {
    host = new URL(url).hostname.toLowerCase().replace(/^www\./, '');
  } catch {
    return { id: 'DESCONHECIDA', nome: 'Fonte desconhecida', tipo: 'DESCONHECIDA', prioridade: 99, bloqueado: false, dominio: null };
  }

  const fonte = SOURCES.find((item) => item.dominios.some((dominio) => host === dominio || host.endsWith(`.${dominio}`)));
  if (!fonte) {
    return { id: 'DESCONHECIDA', nome: 'Fonte desconhecida', tipo: 'DESCONHECIDA', prioridade: 99, bloqueado: false, dominio: host };
  }

  return { ...fonte, dominio: host };
}

module.exports = { SOURCES, identificarFonte };
