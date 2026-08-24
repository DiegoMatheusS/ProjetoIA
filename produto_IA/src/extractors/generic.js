const {
  textoLimpo,
  moedaParaNumero,
  urlAbsoluta,
} = require("../utils/normalize");

async function primeiroTexto(page, seletores) {
  for (const seletor of seletores) {
    try {
      const el = page.locator(seletor).first();
      if (await el.count()) {
        const texto = textoLimpo(await el.textContent());
        if (texto) return texto;
      }
    } catch {}
  }
  return null;
}

async function primeiroAtributo(page, seletores, atributo) {
  for (const seletor of seletores) {
    try {
      const el = page.locator(seletor).first();
      if (await el.count()) {
        const valor = textoLimpo(await el.getAttribute(atributo));
        if (valor) return valor;
      }
    } catch {}
  }
  return null;
}

function procurarProdutoJsonLd(valor) {
  if (!valor) return null;

  if (Array.isArray(valor)) {
    for (const item of valor) {
      const achado = procurarProdutoJsonLd(item);
      if (achado) return achado;
    }
    return null;
  }

  if (typeof valor !== "object") return null;

  const tipo = valor["@type"];
  if (
    tipo === "Product" ||
    (Array.isArray(tipo) && tipo.includes("Product"))
  ) {
    return valor;
  }

  if (valor["@graph"]) {
    const achado = procurarProdutoJsonLd(valor["@graph"]);
    if (achado) return achado;
  }

  for (const item of Object.values(valor)) {
    if (item && typeof item === "object") {
      const achado = procurarProdutoJsonLd(item);
      if (achado) return achado;
    }
  }

  return null;
}

async function lerJsonLd(page) {
  const scripts = await page.locator('script[type="application/ld+json"]').allTextContents();

  for (const conteudo of scripts) {
    try {
      const json = JSON.parse(conteudo);
      const produto = procurarProdutoJsonLd(json);
      if (produto) return produto;
    } catch {
      // Alguns sites têm JSON-LD inválido; seguimos para os outros métodos.
    }
  }

  return null;
}

function extrairOfertaJsonLd(produto) {
  if (!produto) return null;

  const offers = Array.isArray(produto.offers)
    ? produto.offers[0]
    : produto.offers;

  if (!offers) return null;

  return {
    preco:
      moedaParaNumero(offers.price) ??
      moedaParaNumero(offers.lowPrice) ??
      moedaParaNumero(offers.highPrice),
    moeda: textoLimpo(offers.priceCurrency),
    disponibilidade: textoLimpo(offers.availability),
    vendedor:
      textoLimpo(offers.seller?.name) ??
      textoLimpo(offers.seller),
  };
}

async function extrairGenerico(page, url) {
  const jsonLd = await lerJsonLd(page);
  const ofertaLd = extrairOfertaJsonLd(jsonLd);

  const nome =
    textoLimpo(jsonLd?.name) ??
    (await primeiroAtributo(page, [
      'meta[property="og:title"]',
      'meta[name="twitter:title"]',
    ], "content")) ??
    (await primeiroTexto(page, ["h1"]));

  let preco =
    ofertaLd?.preco ??
    moedaParaNumero(
      await primeiroAtributo(page, [
        'meta[property="product:price:amount"]',
        'meta[itemprop="price"]',
      ], "content")
    );

  if (preco == null) {
    const textoPreco = await primeiroTexto(page, [
      '[itemprop="price"]',
      '[data-testid*="price" i]',
      '[class*="price" i]',
      '[class*="preco" i]',
      '[id*="price" i]',
      '[id*="preco" i]',
    ]);
    preco = moedaParaNumero(textoPreco);
  }

  let imagem = null;

  if (jsonLd?.image) {
    if (Array.isArray(jsonLd.image)) {
      imagem =
        typeof jsonLd.image[0] === "string"
          ? jsonLd.image[0]
          : jsonLd.image[0]?.url;
    } else if (typeof jsonLd.image === "string") {
      imagem = jsonLd.image;
    } else {
      imagem = jsonLd.image?.url;
    }
  }

  imagem =
    imagem ??
    (await primeiroAtributo(page, [
      'meta[property="og:image"]',
      'meta[name="twitter:image"]',
    ], "content"));

  const marca =
    textoLimpo(jsonLd?.brand?.name) ??
    textoLimpo(jsonLd?.brand) ??
    null;

  const sku =
    textoLimpo(jsonLd?.sku) ??
    textoLimpo(jsonLd?.mpn) ??
    null;

  const descricao =
    textoLimpo(jsonLd?.description) ??
    (await primeiroAtributo(page, [
      'meta[name="description"]',
      'meta[property="og:description"]',
    ], "content"));

  const disponibilidadeTexto = ofertaLd?.disponibilidade?.toLowerCase() || null;
  let disponivel = null;

  if (disponibilidadeTexto) {
    if (
      disponibilidadeTexto.includes("instock") ||
      disponibilidadeTexto.includes("in_stock") ||
      disponibilidadeTexto.includes("available")
    ) {
      disponivel = true;
    } else if (
      disponibilidadeTexto.includes("outofstock") ||
      disponibilidadeTexto.includes("out_of_stock") ||
      disponibilidadeTexto.includes("soldout")
    ) {
      disponivel = false;
    }
  }

  const tituloPagina = textoLimpo(await page.title());

  return {
    nome,
    marca,
    sku,
    preco,
    moeda: ofertaLd?.moeda ?? "BRL",
    disponivel,
    imagem: urlAbsoluta(imagem, url),
    descricao,
    url,
    tituloPagina,
    fonte: "generic",
    coletadoEm: new Date().toISOString(),
  };
}

module.exports = { extrairGenerico };
