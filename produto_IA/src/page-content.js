function normalizarTexto(texto) {
  return String(texto || '')
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function trechoEntreMarcadores(texto, inicios, finais) {
  const fonte = String(texto || '');
  const lower = fonte.toLowerCase();
  let inicio = -1;

  for (const marcador of inicios) {
    const pos = lower.indexOf(marcador.toLowerCase());
    if (pos >= 0 && (inicio < 0 || pos < inicio)) inicio = pos;
  }

  if (inicio < 0) return '';

  let fim = fonte.length;
  for (const marcador of finais) {
    const pos = lower.indexOf(marcador.toLowerCase(), inicio + 1);
    if (pos >= 0 && pos < fim) fim = pos;
  }

  return fonte.slice(inicio, fim).trim();
}

async function extrairConteudoPagina(page) {
  const bruto = await page.locator('body').innerText().catch(() => '');
  const texto = normalizarTexto(bruto);

  const tecnico = trechoEntreMarcadores(
    texto,
    [
      'ficha técnica',
      'ficha tecnica',
      'especificações',
      'especificacoes',
      'especificações técnicas',
      'especificacoes tecnicas',
      'technical specifications',
      'specifications',
    ],
    [
      'avaliações dos clientes',
      'avaliacoes dos clientes',
      'perguntas e respostas',
      'comentários',
      'comentarios',
      'reviews',
      'customer reviews',
    ],
  );

  return {
    textoCompleto: texto,
    textoTecnico: tecnico || texto.slice(0, 50000),
  };
}

module.exports = { extrairConteudoPagina, normalizarTexto, trechoEntreMarcadores };
