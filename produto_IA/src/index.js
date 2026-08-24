const { abrirPagina } = require('./browser');
const { extrairGenerico } = require('./extractors/generic');
const { detectarCategoria } = require('./category');
const { extrairPorCategoria } = require('./specs-extractor');
const { SCHEMAS, REQUIRED_FIELDS } = require('./backend-schemas');
const { identificarFonte } = require('./source-profiles');
const { extrairConteudoPagina } = require('./page-content');
const { consultarMarketplace } = require('./marketplace');

function extrairVendedor(texto) {
  const fonte = String(texto || '');
  const match = fonte.match(/vendido\s+por\s+([^\n|]+?)(?:\s+e\s+entregue|\s*$)/i);
  return match?.[1]?.trim() || null;
}

function camposAusentes(categoria, specs) {
  const obrigatorios = REQUIRED_FIELDS[categoria] || [];
  return obrigatorios.filter((campo) => {
    const valor = specs?.[campo];
    return valor === undefined || valor === null || valor === '' || (Array.isArray(valor) && valor.length === 0);
  });
}

function validarEspecificacoesBasicas(categoria, specs) {
  const avisos = [];
  if (categoria === 'PROCESSADOR' && specs.tdpWatts !== undefined && specs.tdpWatts > 10000) avisos.push('tdpWatts fora de uma faixa plausível.');
  if (categoria === 'MEMORIA_RAM' && specs.frequenciaMhz !== undefined && specs.frequenciaMhz > 20000) avisos.push('frequenciaMhz fora de uma faixa plausível.');
  if (categoria === 'PLACA_VIDEO' && specs.clockBaseMhz !== undefined && specs.clockBoostMhz !== undefined && specs.clockBaseMhz > specs.clockBoostMhz) avisos.push('clockBaseMhz maior que clockBoostMhz.');
  if (categoria === 'VENTOINHA' && specs.rpmMinima !== undefined && specs.rpmMaxima !== undefined && specs.rpmMinima > specs.rpmMaxima) avisos.push('rpmMinima maior que rpmMaxima.');
  if (categoria === 'ARMAZENAMENTO' && specs.formato === 'M2' && specs.tamanhoM2Mm !== undefined && ![2230, 2242, 2260, 2280, 22110].includes(specs.tamanhoM2Mm)) avisos.push('tamanhoM2Mm não reconhecido.');
  return avisos;
}

async function main() {
  const args = process.argv.slice(2);
  const url = args[0];
  const categoriaForcada = args.find((arg) => SCHEMAS[String(arg).toUpperCase()]) || null;

  if (!url) {
    console.error('Uso: npm start -- "https://site.com/produto" [CATEGORIA]');
    process.exit(1);
  }

  try {
    new URL(url);
  } catch {
    console.error('URL inválida.');
    process.exit(1);
  }

  const fonte = identificarFonte(url);
  // Marketplaces agora são suportados. A API é opcional: sem credenciais, o scraper continua como fallback.

  let browser;

  try {
    const sessao = await abrirPagina(url);
    browser = sessao.browser;
    const page = sessao.page;

    const finalUrl = page.url();
    const marketplace = await consultarMarketplace(url, finalUrl);
    const produto = await extrairGenerico(page, finalUrl);
    const conteudo = await extrairConteudoPagina(page);

    // Quando uma API oficial estiver disponível e configurada, ela tem prioridade
    // para preço, imagem, identificadores e metadados do marketplace.
    const produtoApi = marketplace.usado ? {
      nome: marketplace.titulo,
      marca: marketplace.marca,
      modelo: marketplace.modelo,
      descricao: marketplace.descricao,
      mpn: marketplace.modelo,
      gtin: marketplace.gtin,
      imagem: marketplace.imagemUrl,
      preco: marketplace.preco,
      precoAnterior: marketplace.precoAnterior,
      moeda: marketplace.moeda,
      disponivel: marketplace.disponivel,
      url: marketplace.productUrl || finalUrl,
      coletadoEm: new Date().toISOString(),
    } : null;

    const produtoFinal = produtoApi ? {
      ...produto,
      ...Object.fromEntries(Object.entries(produtoApi).filter(([, v]) => v !== null && v !== undefined && v !== '')),
      // A URL que o usuário forneceu continua sendo preservada abaixo como URL original/oferta.
    } : produto;
    const textoApi = marketplace.usado ? [marketplace.titulo, marketplace.atributosTexto, marketplace.loja].filter(Boolean).join('\n') : '';
    const textoAnalise = [produtoFinal.nome, produtoFinal.descricao, produtoFinal.tituloPagina, textoApi, conteudo.textoTecnico]
      .filter(Boolean)
      .join('\n')
      .slice(0, 150000);

    const categoria = detectarCategoria(textoAnalise, categoriaForcada);
    const schema = categoria ? SCHEMAS[categoria] : null;
    const textoSpecs = [conteudo.textoTecnico, textoApi].filter(Boolean).join('\n');
    const specs = categoria ? extrairPorCategoria(categoria, textoSpecs || textoAnalise) : {};
    const vendedorNome = marketplace.usado && marketplace.loja ? marketplace.loja : extrairVendedor(conteudo.textoCompleto);
    const ausentes = categoria ? camposAusentes(categoria, specs) : [];
    const avisos = categoria ? validarEspecificacoesBasicas(categoria, specs) : [];

    const base = {
      nome: produtoFinal.nome,
      marca: produtoFinal.marca,
      modelo: produtoFinal.modelo || null,
      descricao: produtoFinal.descricao,
      mpn: produtoFinal.mpn || produtoFinal.modelo || null,
      gtin: produtoFinal.gtin || null,
      imagemUrl: produtoFinal.imagem,
    };

    if (categoria && schema?.tipoCadastro === 'HARDWARE') base.categoria = categoria;
    const payloadParcial = { ...base };
    if (schema?.campo) payloadParcial[schema.campo] = specs;

    const resultado = {
      categoriaDetectada: categoria,
      tipoCadastro: schema?.tipoCadastro ?? null,
      fonte: {
        id: fonte.id,
        nome: fonte.nome,
        tipo: fonte.tipo,
        dominio: fonte.dominio,
        prioridade: fonte.prioridade,
      },
      vendedorDetectado: vendedorNome,
      payloadParcialBackend: payloadParcial,
      ofertaColetada: {
        preco: produtoFinal.preco,
        precoAnterior: produtoFinal.precoAnterior,
        moeda: produtoFinal.moeda,
        disponivel: produtoFinal.disponivel,
        urlOriginal: url,
        urlProduto: produtoFinal.url,
        vendedorNome,
      },
      especificacoesEncontradas: specs,
      camposEspecificacaoEsperados: schema?.campos ?? [],
      camposObrigatoriosAusentes: ausentes,
      avisosValidacao: avisos,
      marketplace: {
        plataforma: marketplace.plataforma,
        apiUsada: marketplace.usado,
        motivo: marketplace.motivo || null,
        itemId: marketplace.itemId || null,
        shopId: marketplace.shopId || null,
        affiliateUrl: marketplace.affiliateUrl || null,
        descontoPercentual: marketplace.descontoPercentual ?? null,
        comissaoPercentual: marketplace.comissaoPercentual ?? null,
        comissao: marketplace.comissao ?? null,
      },
      estrategia: {
        mercadoLivre: 'API_OPCIONAL_COM_FALLBACK',
        imagem: 'SOMENTE_URL',
        fontePrincipal: marketplace.usado ? marketplace.fonte : fonte.tipo === 'FABRICANTE' ? 'FABRICANTE' : fonte.tipo === 'LOJA' ? 'LOJA' : fonte.tipo === 'MARKETPLACE' ? 'MARKETPLACE_SCRAPER' : 'GENERICA',
        iaAindaNaoUtilizada: true,
        mercadoLivreApi: 'MERCADO_LIVRE_API',
        shopeeApi: 'SHOPEE_AFFILIATE_API',
      },
      coletadoEm: produtoFinal.coletadoEm,
    };

    console.log(JSON.stringify(resultado, null, 2));
  } catch (erro) {
    console.error('Falha ao coletar produto:');
    console.error(erro?.message || erro);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
}

main();
