const { chromium } = require("playwright");

async function abrirPagina(url) {
  const browser = await chromium.launch({
    headless: true,
  });

  const context = await browser.newContext({
    locale: "pt-BR",
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
  });

  const page = await context.newPage();

  await page.goto(url, {
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });

  // Dá um pequeno tempo para lojas que carregam preço via JavaScript.
  await page.waitForTimeout(1500);

  return { browser, page };
}

module.exports = { abrirPagina };
