(() => {
  const nativeFetch = window.fetch.bind(window);

  window.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input?.url;
    if (!url || !url.endsWith("/extensao/importar-oferta")) {
      return nativeFetch(input, init);
    }

    let body = {};
    try {
      body = init.body ? JSON.parse(init.body) : {};
    } catch {
      body = {};
    }

    // Recaptura a aba no momento do envio. Isso evita reutilizar ASIN/preço de
    // uma página anterior quando o usuário troca de produto com o popup aberto.
    try {
      const liveCapture = await chrome.runtime.sendMessage({
        type: "GET_CURRENT_PRODUCT_DATA",
      });
      if (
        liveCapture?.url === body.urlProduto &&
        liveCapture?.dados &&
        typeof liveCapture.dados === "object"
      ) {
        body.dadosPagina = liveCapture.dados;
      } else {
        const saved = await chrome.storage.local.get(["lastProductCapture"]);
        const capture = saved.lastProductCapture;
        if (
          capture?.url === body.urlProduto &&
          capture?.dados &&
          typeof capture.dados === "object"
        ) {
          body.dadosPagina = capture.dados;
        }
      }
    } catch {
      // O servidor v2 ainda consegue completar via coleta/IA sem a captura local.
    }

    const v2Url = url.replace(
      /\/extensao\/importar-oferta$/,
      "/extensao/importar-oferta-v2",
    );
    const response = await nativeFetch(v2Url, {
      ...init,
      body: JSON.stringify(body),
    });

    let data;
    try {
      data = await response.clone().json();
    } catch {
      return response;
    }

    if (response.ok && data && typeof data === "object") {
      // A interface existente já possui mensagem para NOVA_OFERTA_CRIADA.
      // Mantemos o status detalhado em statusFluxo para diagnóstico.
      if (data.status === "ITEM_EXISTENTE_OFERTA_CRIADA") {
        data.statusFluxo = data.status;
        data.status = "NOVA_OFERTA_CRIADA";
      }

      if (data.previa && typeof data.previa === "object") {
        const specs =
          data.previa.especificacoes &&
          typeof data.previa.especificacoes === "object"
            ? { ...data.previa.especificacoes }
            : {};
        if (data.previa.asin) specs.ASIN = data.previa.asin;
        if (data.previa.gtin) specs.GTIN = data.previa.gtin;
        if (data.previa.mpn) specs.MPN = data.previa.mpn;
        specs.Fluxo =
          data.completouComIa === false
            ? "Item já existente — somente oferta criada/atualizada"
            : "Completar com IA";
        data.previa.especificacoes = specs;
      }
    }

    const headers = new Headers(response.headers);
    headers.delete("content-length");
    headers.delete("content-encoding");
    headers.set("content-type", "application/json; charset=utf-8");

    return new Response(JSON.stringify(data), {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  };
})();
