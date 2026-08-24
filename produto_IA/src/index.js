const { abrirPagina } = require('./browser');
const { extrairGenerico } = require('./extractors/generic');
const { detectarCategoria } = require('./category');
const { extrairPorCategoria } = require('./specs-extractor');
const { SCHEMAS } = require('./backend-schemas');

async function main() {
  const url = process.argv[2];
  const categoriaForcada = process.argv[3];

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

  let browser;

  try {
    const sessao = await abrirPagina(url);
    browser = sessao.browser;
    const page = sessao.page;

    const produto = await extrairGenerico(page, url);
    const textoPagina = await page.locator('body').innerText().catch(() => '');
    const textoAnalise = [produto.nome, produto.descricao, produto.tituloPagina, textoPagina]
      .filter(Boolean)
      .join('\n')
      .slice(0, 150000);

    const categoria = detectarCategoria(textoAnalise, categoriaForcada);
    const schema = categoria ? SCHEMAS[categoria] : null;
    const specs = categoria ? extrairPorCategoria(categoria, textoAnalise) : {};

    const base = {
      nome: produto.nome,
      marca: produto.marca,
      modelo: null,
      descricao: produto.descricao,
      mpn: produto.sku || null,
      gtin: null,
      imagemUrl: produto.imagem
    };

    if (categoria && schema?.tipoCadastro === 'HARDWARE') {
      base.categoria = categoria;
    }

    const payloadParcial = { ...base };
    if (schema?.campo && Object.keys(specs).length) {
      payloadParcial[schema.campo] = specs;
    }

    const resultado = {
      categoriaDetectada: categoria,
      tipoCadastro: schema?.tipoCadastro ?? null,
      payloadParcialBackend: payloadParcial,
      ofertaColetada: {
        preco: produto.preco,
        moeda: produto.moeda,
        disponivel: produto.disponivel,
        urlOriginal: produto.url
      },
      camposEspecificacaoEsperados: schema?.campos ?? [],
      coletadoEm: produto.coletadoEm
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
