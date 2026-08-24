const crypto = require('crypto');
const { textoLimpo } = require('./utils/normalize');

function extrairIdsShopee(url) {
  const texto = String(url || '');
  let shopId = null;
  let itemId = null;

  let match = texto.match(/\/product\/(\d+)\/(\d+)/i);
  if (match) {
    shopId = match[1];
    itemId = match[2];
  }

  if (!itemId) {
    match = texto.match(/-i\.(\d+)\.(\d+)(?:[/?#]|$)/i);
    if (match) {
      shopId = match[1];
      itemId = match[2];
    }
  }

  if (!itemId) {
    try {
      const parsed = new URL(texto);
      shopId = parsed.searchParams.get('shopid') || parsed.searchParams.get('shop_id') || shopId;
      itemId = parsed.searchParams.get('itemid') || parsed.searchParams.get('item_id') || itemId;
    } catch {}
  }

  return { shopId, itemId };
}

function assinatura(appId, timestamp, body, secret) {
  return crypto
    .createHash('sha256')
    .update(`${appId}${timestamp}${body}${secret}`)
    .digest('hex');
}

async function consultarShopeeAffiliate(url, options = {}) {
  const finalUrl = options.finalUrl || url;
  const ids = extrairIdsShopee(finalUrl);
  if (!ids.itemId) return { usado: false, motivo: 'ITEM_ID_NAO_ENCONTRADO' };

  const appId = process.env.SHOPEE_AFFILIATE_APP_ID || '';
  const secret = process.env.SHOPEE_AFFILIATE_SECRET || '';

  if (!appId || !secret) {
    return {
      usado: false,
      itemId: ids.itemId,
      shopId: ids.shopId,
      motivo: 'SHOPEE_AFFILIATE_CREDENCIAIS_NAO_CONFIGURADAS',
    };
  }

  const query = `query ProductOffer($itemId: Int64${ids.shopId ? ', $shopId: Int64' : ''}) {\n  productOfferV2(itemId: $itemId${ids.shopId ? ', shopId: $shopId' : ''}, listType: 0, page: 1, limit: 1) {\n    nodes {\n      itemId productName productLink offerLink imageUrl priceMin priceMax priceDiscountRate sales ratingStar commissionRate sellerCommissionRate shopeeCommissionRate commission shopId shopName shopType periodStartTime periodEndTime\n    }\n    pageInfo { page limit hasNextPage }\n  }\n}`;

  const variables = { itemId: Number(ids.itemId) };
  if (ids.shopId) variables.shopId = Number(ids.shopId);

  const payload = JSON.stringify({ query, variables, operationName: 'ProductOffer' });
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const signature = assinatura(appId, timestamp, payload, secret);

  const response = await fetch('https://open-api.affiliate.shopee.com.br/graphql', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `SHA256 Credential=${appId},Timestamp=${timestamp},Signature=${signature}`,
    },
    body: payload,
  });

  const text = await response.text();
  let data = null;
  try { data = JSON.parse(text); } catch {}

  if (!response.ok || data?.errors?.length) {
    const error = data?.errors?.[0]?.message || `HTTP ${response.status}`;
    return {
      usado: false,
      itemId: ids.itemId,
      shopId: ids.shopId,
      motivo: 'SHOPEE_API_ERRO',
      erro: error,
    };
  }

  const node = data?.data?.productOfferV2?.nodes?.[0];
  if (!node) {
    return {
      usado: false,
      itemId: ids.itemId,
      shopId: ids.shopId,
      motivo: 'PRODUTO_NAO_ENCONTRADO_NA_API',
    };
  }

  const preco = Number(node.priceMin);
  const desconto = Number(node.priceDiscountRate);
  const precoAnterior = Number.isFinite(preco) && desconto > 0
    ? Number((preco / (1 - desconto / 100)).toFixed(2))
    : null;

  return {
    usado: true,
    fonte: 'SHOPEE_AFFILIATE_API',
    itemId: String(node.itemId ?? ids.itemId),
    shopId: node.shopId != null ? String(node.shopId) : ids.shopId,
    titulo: textoLimpo(node.productName),
    marca: null,
    modelo: null,
    gtin: null,
    imagemUrl: textoLimpo(node.imageUrl),
    descricao: null,
    preco: Number.isFinite(preco) ? preco : null,
    precoMax: Number.isFinite(Number(node.priceMax)) ? Number(node.priceMax) : null,
    precoAnterior,
    descontoPercentual: Number.isFinite(desconto) ? desconto : null,
    moeda: 'BRL',
    disponivel: true,
    productUrl: textoLimpo(node.productLink),
    affiliateUrl: textoLimpo(node.offerLink),
    loja: textoLimpo(node.shopName),
    comissaoPercentual: Number.isFinite(Number(node.commissionRate)) ? Number(node.commissionRate) * 100 : null,
    comissao: Number.isFinite(Number(node.commission)) ? Number(node.commission) : null,
    vendas: Number.isFinite(Number(node.sales)) ? Number(node.sales) : null,
    avaliacao: Number.isFinite(Number(node.ratingStar)) ? Number(node.ratingStar) : null,
    raw: node,
  };
}

module.exports = { consultarShopeeAffiliate, extrairIdsShopee };
