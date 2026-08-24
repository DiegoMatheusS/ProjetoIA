const { abrirPagina } = require("./browser");
const { extrairGenerico } = require("./extractors/generic");

async function main() {
  const url = process.argv[2];

  if (!url) {
    console.error('Uso: npm start -- "https://site.com/produto"');
    process.exit(1);
  }

  try {
    new URL(url);
  } catch {
    console.error("URL inválida.");
    process.exit(1);
  }

  let browser;

  try {
    const sessao = await abrirPagina(url);
    browser = sessao.browser;

    const produto = await extrairGenerico(sessao.page, url);

    console.log(JSON.stringify(produto, null, 2));
  } catch (erro) {
    console.error("Falha ao coletar produto:");
    console.error(erro?.message || erro);
    process.exitCode = 1;
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

main();
