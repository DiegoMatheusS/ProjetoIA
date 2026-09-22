const DEFAULT_API_URL = "https://projetoia-production.up.railway.app";

const els = {
  productUrl: document.querySelector("#productUrl"),
  affiliateUrl: document.querySelector("#affiliateUrl"),
  apiUrl: document.querySelector("#apiUrl"),
  apiKey: document.querySelector("#apiKey"),
  currentTab: document.querySelector("#currentTab"),
  pasteAffiliate: document.querySelector("#pasteAffiliate"),
  send: document.querySelector("#send"),
  saveConfig: document.querySelector("#saveConfig"),
  pinAlwaysOnTop: document.querySelector("#pinAlwaysOnTop"),
  result: document.querySelector("#result"),
};

function cleanBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function isHttpUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function showResult(message, type = "success") {
  els.result.className = `result ${type}`;
  els.result.textContent = message;
}

async function loadCurrentTab() {
  try {
    const response = await chrome.runtime.sendMessage({
      type: "GET_CURRENT_PRODUCT_URL",
    });
    if (response?.url && /^https?:/i.test(response.url)) {
      els.productUrl.value = response.url;
      return;
    }
  } catch {
    // Usa o último endereço salvo como fallback.
  }

  const saved = await chrome.storage.local.get(["lastProductUrl"]);
  if (saved.lastProductUrl && /^https?:/i.test(saved.lastProductUrl)) {
    els.productUrl.value = saved.lastProductUrl;
  }
}

async function loadConfig() {
  const saved = await chrome.storage.local.get(["apiUrl", "apiKey"]);
  els.apiUrl.value = saved.apiUrl || DEFAULT_API_URL;
  els.apiKey.value = saved.apiKey || "";

  if (!saved.apiUrl) {
    await chrome.storage.local.set({ apiUrl: DEFAULT_API_URL });
  }
}

async function saveConfig() {
  const apiUrl = cleanBaseUrl(els.apiUrl.value || DEFAULT_API_URL);
  const apiKey = String(els.apiKey.value || "").trim();

  if (!isHttpUrl(apiUrl)) {
    showResult("Informe uma URL válida para a Produto IA.", "warning");
    return false;
  }

  if (!apiKey) {
    showResult("Informe a chave PRODUTO_IA_API_KEY.", "warning");
    return false;
  }

  await chrome.storage.local.set({ apiUrl, apiKey });
  els.apiUrl.value = apiUrl;
  showResult("Configuração salva no Chrome.", "success");
  return true;
}

async function pinAlwaysOnTop() {
  if (!("documentPictureInPicture" in window)) {
    showResult(
      "Este Chrome não oferece o modo de janela sempre sobreposta.",
      "warning",
    );
    return;
  }

  try {
    const app = document.querySelector(".app");
    const sourceWindow = await chrome.windows.getCurrent();

    const pipWindow = await documentPictureInPicture.requestWindow({
      width: 500,
      height: 720,
      disallowReturnToOpener: true,
    });

    for (const styleSheet of [...document.styleSheets]) {
      try {
        const cssText = [...styleSheet.cssRules]
          .map((rule) => rule.cssText)
          .join("\n");
        const style = pipWindow.document.createElement("style");
        style.textContent = cssText;
        pipWindow.document.head.appendChild(style);
      } catch {
        if (!styleSheet.href) continue;
        const link = pipWindow.document.createElement("link");
        link.rel = "stylesheet";
        link.href = styleSheet.href;
        pipWindow.document.head.appendChild(link);
      }
    }

    const favicon = pipWindow.document.createElement("link");
    favicon.rel = "icon";
    favicon.type = "image/png";
    favicon.href = chrome.runtime.getURL("icons/icon32.png");
    pipWindow.document.head.appendChild(favicon);
    pipWindow.document.title = "Criabyte — Enviar oferta";
    pipWindow.document.documentElement.style.background = "#ffffff";
    pipWindow.document.body.style.margin = "0";
    pipWindow.document.body.style.background = "#ffffff";

    app.classList.add("pip-mode");
    pipWindow.document.body.appendChild(app);

    if (sourceWindow?.id !== undefined) {
      try {
        await chrome.windows.update(sourceWindow.id, { state: "minimized" });
      } catch {
        // O PiP já continua sobreposto mesmo se a janela de origem não minimizar.
      }
    }

    pipWindow.addEventListener(
      "pagehide",
      async () => {
        if (sourceWindow?.id === undefined) return;
        try {
          await chrome.windows.remove(sourceWindow.id);
        } catch {
          // A janela de origem pode já ter sido encerrada.
        }
      },
      { once: true },
    );
  } catch (error) {
    showResult(
      error?.message ||
        "Não foi possível ativar o modo sempre sobreposto.",
      "warning",
    );
  }
}

function resultMessage(data) {
  const hardware = data?.hardware?.nome ? ` — ${data.hardware.nome}` : "";
  const partner = data?.parceiro?.nome ? ` (${data.parceiro.nome})` : "";

  switch (data?.status) {
    case "OFERTA_ATUALIZADA":
      return `Oferta existente atualizada${hardware}${partner}.`;
    case "NOVA_OFERTA_CRIADA":
      return `Nova oferta adicionada${hardware}${partner}.`;
    case "HARDWARE_E_OFERTA_CRIADOS":
      return `Novo hardware cadastrado e oferta criada${hardware}${partner}. Ficou como rascunho para revisão.`;
    case "REVISAO_NECESSARIA":
      return data?.motivo || "O produto precisa de revisão antes do cadastro.";
    default:
      return "Operação concluída.";
  }
}

els.currentTab.addEventListener("click", async () => {
  await loadCurrentTab();
  if (els.productUrl.value) {
    showResult("Página atualizada com a aba ativa do Chrome.", "success");
  }
});

els.pasteAffiliate.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    els.affiliateUrl.value = text.trim();
  } catch {
    showResult(
      "Não consegui ler a área de transferência. Cole o link manualmente.",
      "warning",
    );
  }
});

els.saveConfig.addEventListener("click", saveConfig);
els.pinAlwaysOnTop?.addEventListener("click", pinAlwaysOnTop);

els.send.addEventListener("click", async () => {
  const productUrl = String(els.productUrl.value || "").trim();
  const affiliateUrl = String(els.affiliateUrl.value || "").trim();
  const apiUrl = cleanBaseUrl(els.apiUrl.value || DEFAULT_API_URL);
  const apiKey = String(els.apiKey.value || "").trim();

  if (!isHttpUrl(productUrl)) {
    showResult("A página do produto é inválida.", "warning");
    return;
  }
  if (!isHttpUrl(affiliateUrl)) {
    showResult("Cole um link afiliado válido.", "warning");
    return;
  }
  if (!isHttpUrl(apiUrl)) {
    showResult("A URL da Produto IA é inválida.", "warning");
    return;
  }
  if (!apiKey) {
    showResult("Abra Configuração e informe a chave da API.", "warning");
    return;
  }

  await chrome.storage.local.set({ apiUrl, apiKey });

  els.send.disabled = true;
  els.send.textContent = "Enviando...";
  showResult("Analisando produto e verificando o Criabyte...", "success");

  try {
    const response = await fetch(`${apiUrl}/extensao/importar-oferta`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify({
        urlProduto: productUrl,
        urlAfiliada: affiliateUrl,
      }),
    });

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok) {
      const detail = data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : detail?.mensagem ||
            detail?.message ||
            data?.message ||
            `Erro HTTP ${response.status}`;
      throw new Error(message);
    }

    const warning = data?.status === "REVISAO_NECESSARIA";
    showResult(resultMessage(data), warning ? "warning" : "success");
  } catch (error) {
    showResult(
      error?.message || "Falha ao enviar a oferta para o Criabyte.",
      "error",
    );
  } finally {
    els.send.disabled = false;
    els.send.textContent = "Enviar para Criabyte";
  }
});

Promise.all([loadConfig(), loadCurrentTab()]).catch(() => {});
