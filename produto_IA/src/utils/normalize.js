function textoLimpo(valor) {
  if (valor == null) return null;
  const texto = String(valor).replace(/\s+/g, " ").trim();
  return texto || null;
}

function moedaParaNumero(valor) {
  if (valor == null) return null;

  let texto = String(valor)
    .replace(/\u00a0/g, " ")
    .replace(/[^\d,.\-]/g, "")
    .trim();

  if (!texto) return null;

  const temVirgula = texto.includes(",");
  const temPonto = texto.includes(".");

  if (temVirgula && temPonto) {
    // Padrão BR: 1.234,56
    if (texto.lastIndexOf(",") > texto.lastIndexOf(".")) {
      texto = texto.replace(/\./g, "").replace(",", ".");
    } else {
      // Padrão US: 1,234.56
      texto = texto.replace(/,/g, "");
    }
  } else if (temVirgula) {
    texto = texto.replace(/\./g, "").replace(",", ".");
  }

  const numero = Number(texto);
  return Number.isFinite(numero) ? numero : null;
}

function urlAbsoluta(valor, baseUrl) {
  if (!valor) return null;
  try {
    return new URL(valor, baseUrl).toString();
  } catch {
    return null;
  }
}

module.exports = {
  textoLimpo,
  moedaParaNumero,
  urlAbsoluta,
};
