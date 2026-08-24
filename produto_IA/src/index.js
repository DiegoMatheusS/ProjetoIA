const { abrirPagina } = require('./browser');
const { extrairGenerico } = require('./extractors/generic');
const { detectarCategoria } = require('./category');
const { extrairPorCategoria } = require('./specs-extractor');
const { SCHEMAS, REQUIRED_FIELDS } = require('./backend-schemas');
const { identificarFonte } = require('./source-profiles');
const { extrairConteudoPagina } = require('./page-content');

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
  if (fonte.bloqueado) {
    console.error(`Fonte bloqueada para coleta: ${fonte.nome}. Use uma loja ou fabricante como fonte principal.`);
    process.exit(2);
  }

  let browser;

  try {
    const sessao = await abrirPagina(url);
    browser = sessao.browser;
    const page = sessao.page;

    const produto = await extrairGenerico(page, url);
    const conteudo = await extrairConteudoPagina(page);
    const textoAnalise = [produto.nome, produto.descricao, produto.tituloPagina, conteudo.textoTecnico]
      .filter(Boolean)
      .join('\n')
      .slice(0, 150000);

    const categoria = detectarCategoria(textoAnalise, categoriaForcada);
    const schema = categoria ? SCHEMAS[categoria] : null;
    const specs = categoria ? extrairPorCategoria(categoria, conteudo.textoTecnico || textoAnalise) : {};
    const vendedorNome = extrairVendedor(conteudo.textoCompleto);
    const ausentes = categoria ? camposAusentes(categoria, specs) : [];
    const avisos = categoria ? validarEspecificacoesBasicas(categoria, specs) : [];

    const base = {
      nome: produto.nome,
      marca: produto.marca,
      modelo: produto.modelo || null,
      descricao: produto.descricao,
      mpn: produto.mpn || produto.modelo || null,
      gtin: null,
      imagemUrl: produto.imagem,
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
        preco: produto.preco,
        precoAnterior: produto.precoAnterior,
        moeda: produto.moeda,
        disponivel: produto.disponivel,
        urlOriginal: produto.url,
        vendedorNome,
      },
      especificacoesEncontradas: specs,
      camposEspecificacaoEsperados: schema?.campos ?? [],
      camposObrigatoriosAusentes: ausentes,
      avisosValidacao: avisos,
      estrategia: {
        mercadoLivre: 'BLOQUEADO',
        imagem: 'SOMENTE_URL',
        fontePrincipal: fonte.tipo === 'FABRICANTE' ? 'FABRICANTE' : fonte.tipo === 'LOJA' ? 'LOJA' : 'GENERICA',
        iaAindaNaoUtilizada: true,
      },
      coletadoEm: produto.coletadoEm,
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
