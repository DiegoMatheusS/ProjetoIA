const { moedaParaNumero, textoLimpo, urlAbsoluta } = require('./utils/normalize');

function extrairItemId(url) {
  const texto = String(url || '');
  const match = texto.match(/(?:^|[^A-Z])(MLB\d{6,})(?:[^\d]|$)/i);
  return match ? match[1].toUpperCase() : null;
}

function atributo(item, nomes) {
  const attrs = Array.isArray(item?.attributes) ? item.attributes : [];
  const wanted = nomes.map((n) => n.toLowerCase());
  const achado = attrs.find((a) => {
    const id = String(a?.id || '').toLowerCase();
    const name = String(a?.name || '').toLowerCase();
    return wanted.includes(id) || wanted.includes(name);
  });
  return textoLimpo(achado?.value_name ?? achado?.value_name_struct?.number ?? achado?.value_name_struct?.unit);
}

function atributosComoTexto(item) {
  const attrs = Array.isArray(item?.attributes) ? item.attributes : [];
  return attrs
    .map((a) => {
      const nome = textoLimpo(a?.name || a?.id);
      const valor = textoLimpo(a?.value_name);
      return nome && valor ? `${nome}: ${valor}` : null;
    })
    .filter(Boolean)
    .join('\n');
}

async function mlGet(path, token) {
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`https://api.mercadolibre.com${path}`, { headers });
  const text = await response.text();
  let data = null;
  try { data = JSON.parse(text); } catch {}
  if (!response.ok) {
    const detail = data?.message || data?.error || `HTTP ${response.status}`;
    throw new Error(`Mercado Livre API: ${detail}`);
  }
  return data;
}

async function consultarMercadoLivre(url, options = {}) {
  const itemId = extrairItemId(url) || extrairItemId(options.finalUrl);
  if (!itemId) return { usado: false, motivo: 'ITEM_ID_NAO_ENCONTRADO' };

  const token = process.env.ML_ACCESS_TOKEN || '';
  let item;

  try {
    // include_attributes=all é útil para trazer uma ficha técnica mais completa.
    item = await mlGet(`/items/${encodeURIComponent(itemId)}?include_attributes=all`, token);
  } catch (erro) {
    return {
      usado: false,
      itemId,
      motivo: token ? 'API_INDISPONIVEL_OU_TOKEN_INVALIDO' : 'ML_ACCESS_TOKEN_NAO_CONFIGURADO',
      erro: erro.message,
    };
  }

  let precos = null;
  let salePrice = null;
  try {
    precos = await mlGet(`/items/${encodeURIComponent(itemId)}/prices`, token);
  } catch {}

  try {
    salePrice = await mlGet(`/items/${encodeURIComponent(itemId)}/sale_price?context=channel_marketplace`, token);
  } catch {}

  const prices = Array.isArray(precos?.prices) ? precos.prices : [];
  const promotion = prices.find((p) => p.type === 'promotion' && Number.isFinite(Number(p.amount)));
  const standard = prices.find((p) => p.type === 'standard' && Number.isFinite(Number(p.amount)));

  const precoAtual = Number.isFinite(Number(salePrice?.amount))
    ? Number(salePrice.amount)
    : Number.isFinite(Number(promotion?.amount))
      ? Number(promotion.amount)
      : Number(item?.price);

  const precoAnterior = Number.isFinite(Number(salePrice?.regular_amount))
    ? Number(salePrice.regular_amount)
    : Number.isFinite(Number(promotion?.regular_amount))
      ? Number(promotion.regular_amount)
      : Number.isFinite(Number(standard?.amount)) && Number(standard.amount) > precoAtual
        ? Number(standard.amount)
        : Number.isFinite(Number(item?.original_price)) && Number(item.original_price) > precoAtual
          ? Number(item.original_price)
          : null;

  const imagem = item?.pictures?.[0]?.secure_url || item?.pictures?.[0]?.url || null;
  const marca = atributo(item, ['BRAND', 'Marca', 'Marca do produto']);
  const modelo = atributo(item, ['MODEL', 'Modelo', 'Modelo alfanumérico']);
  const gtin = atributo(item, ['GTIN', 'EAN', 'UPC']);

  return {
    usado: true,
    fonte: 'MERCADO_LIVRE_API',
    itemId,
    titulo: textoLimpo(item?.title),
    marca,
    modelo,
    gtin,
    imagemUrl: urlAbsoluta(imagem, 'https://www.mercadolivre.com.br/'),
    descricao: null,
    preco: Number.isFinite(precoAtual) ? precoAtual : null,
    precoAnterior: Number.isFinite(precoAnterior) ? precoAnterior : null,
    moeda: textoLimpo(salePrice?.currency_id || promotion?.currency_id || standard?.currency_id || item?.currency_id) || 'BRL',
    disponivel: Number(item?.available_quantity) > 0 || item?.status === 'active',
    atributosTexto: atributosComoTexto(item),
    categoriaId: textoLimpo(item?.category_id),
    productUrl: textoLimpo(item?.permalink),
    raw: {
      status: item?.status,
      available_quantity: item?.available_quantity,
      attributes: item?.attributes,
    },
  };
}

module.exports = { consultarMercadoLivre, extrairItemId };
