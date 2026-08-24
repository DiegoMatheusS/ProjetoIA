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

function extrairPrecoAnterior(texto, precoAtual) {
  if (precoAtual == null) return null;

  const fonte = String(texto || '');
  const atualFormatado = precoAtual
    .toFixed(2)
    .replace('.', ',')
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.');

  const posicoes = [];
  let inicio = 0;
  const alvo = atualFormatado;

  while (true) {
    const pos = fonte.indexOf(alvo, inicio);
    if (pos === -1) break;
    posicoes.push(pos);
    inicio = pos + alvo.length;
  }

  let melhor = null;

  for (const pos of posicoes) {
    const antes = fonte.slice(Math.max(0, pos - 120), pos);
    const matches = [...antes.matchAll(/R\$\s*([\d.]+,\d{2})/gi)];
    for (const match of matches) {
      const valor = moedaParaNumero(match[1]);
      if (valor != null && valor > precoAtual) {
        melhor = valor;
      }
    }
    if (melhor != null) return melhor;
  }

  return null;
}

function extrairRotuloSimples(texto, rotulos) {
  const linhas = String(texto || '')
    .split(/\r?\n/)
    .map((linha) => linha.replace(/\s+/g, ' ').trim())
    .filter(Boolean);

  for (const linha of linhas) {
    for (const rotulo of rotulos) {
      const r = String(rotulo).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const padroes = [
        new RegExp(`^${r}\\s*(?:\\||:|;|\\-|–|—)\\s*(.+?)$`, 'i'),
        new RegExp(`^${r}\\s+(.+?)$`, 'i'),
      ];
      for (const regex of padroes) {
        const match = linha.match(regex);
        if (match?.[1]) {
          const valor = match[1].trim();
          if (valor && valor.toLowerCase() !== rotulo.toLowerCase()) return valor;
        }
      }
    }
  }

  return null;
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

  const textoCorpoParaDados = await page.locator('body').innerText().catch(() => '');

  const modelo =
    textoLimpo(jsonLd?.model) ??
    textoLimpo(jsonLd?.modelNumber) ??
    extrairRotuloSimples(textoCorpoParaDados, ['Modelo']) ??
    extrairRotuloSimples(textoCorpoParaDados, ['Referência', 'Referencia']) ??
    null;

  const mpn =
    textoLimpo(jsonLd?.mpn) ??
    textoLimpo(jsonLd?.productID) ??
    extrairRotuloSimples(textoCorpoParaDados, ['Referência', 'Referencia']) ??
    modelo ??
    null;

  const sku =
    textoLimpo(jsonLd?.sku) ??
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
  const precoAnterior = extrairPrecoAnterior(textoCorpoParaDados, preco);

  return {
    nome,
    marca,
    sku,
    modelo,
    mpn,
    preco,
    precoAnterior,
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
