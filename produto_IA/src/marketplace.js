const { consultarMercadoLivre } = require('./apis_mercadolivre');
const { consultarShopeeAffiliate } = require('./apis_shopee');

function ehMercadoLivre(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === 'mercadolivre.com.br' || host.endsWith('.mercadolivre.com.br') || host === 'mercadolibre.com' || host.endsWith('.mercadolibre.com');
  } catch { return false; }
}

function ehShopee(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === 'shopee.com.br' || host.endsWith('.shopee.com.br') || host === 's.shopee.com.br' || host.endsWith('.shopee.com.br');
  } catch { return false; }
}

async function consultarMarketplace(url, finalUrl) {
  if (ehMercadoLivre(finalUrl) || ehMercadoLivre(url)) {
    return {
      plataforma: 'MERCADO_LIVRE',
      ...(await consultarMercadoLivre(url, { finalUrl })),
    };
  }

  if (ehShopee(finalUrl) || ehShopee(url)) {
    return {
      plataforma: 'SHOPEE',
      ...(await consultarShopeeAffiliate(url, { finalUrl })),
    };
  }

  return { plataforma: null, usado: false, motivo: 'NAO_E_MARKETPLACE_SUPORTADO' };
}

module.exports = { consultarMarketplace, ehMercadoLivre, ehShopee };
