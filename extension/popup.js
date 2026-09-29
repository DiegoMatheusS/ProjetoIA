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
  manualPriceBox: document.querySelector("#manualPriceBox"),
  manualPrice: document.querySelector("#manualPrice"),
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

function parseBrlPrice(value) {
  let text = String(value || "")
    .trim()
    .replace(/R\$/gi, "")
    .replace(/\s+/g, "")
    .replace(/[^0-9.,]/g, "");

  if (!text) return null;

  const lastComma = text.lastIndexOf(",");
  const lastDot = text.lastIndexOf(".");

  if (lastComma >= 0 && lastDot >= 0) {
    if (lastComma > lastDot) {
      text = text.replace(/\./g, "").replace(",", ".");
    } else {
      text = text.replace(/,/g, "");
    }
  } else if (lastComma >= 0) {
    text = text.replace(/\./g, "").replace(",", ".");
  } else {
    const dots = (text.match(/\./g) || []).length;
    if (dots === 1) {
      const decimals = text.length - text.lastIndexOf(".") - 1;
      if (decimals === 3) {
        text = text.replace(".", "");
      }
    } else if (dots > 1) {
      text = text.replace(/\./g, "");
    }
  }

  const parsed = Number(text);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 100000000) {
    return null;
  }
  return Math.round(parsed * 100) / 100;
}

async function extractPriceFromCurrentTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return null;

    const [execution] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const amountFromElement = (element) => {
          if (!element) return null;
          const fraction = element.querySelector(
            ".andes-money-amount__fraction, [data-andes-money-amount-fraction='true']",
          );
          const cents = element.querySelector(
            ".andes-money-amount__cents, [data-andes-money-amount-cents='true']",
          );
          const fractionDigits = String(fraction?.textContent || "").replace(/\D/g, "");
          if (!fractionDigits) return null;

          const centsDigits = String(cents?.textContent || "")
            .replace(/\D/g, "")
            .slice(0, 2)
            .padEnd(2, "0");
          const amount = Number(fractionDigits) + (centsDigits ? Number(centsDigits) / 100 : 0);
          return Number.isFinite(amount) && amount > 0 ? Math.round(amount * 100) / 100 : null;
        };

        const selectors = [
          ".ui-pdp-price__second-line .andes-money-amount:not(.andes-money-amount--previous)",
          ".ui-pdp-price__main-container .andes-money-amount:not(.andes-money-amount--previous)",
          "[data-testid='price-part'] .andes-money-amount:not(.andes-money-amount--previous)",
          ".andes-money-amount:not(.andes-money-amount--previous)",
        ];

        const visited = new Set();
        for (const selector of selectors) {
          for (const element of document.querySelectorAll(selector)) {
            if (visited.has(element)) continue;
            visited.add(element);

            if (element.classList.contains("andes-money-amount--previous")) continue;
            const context = String(element.parentElement?.innerText || "").trim();
            if (/\b\d{1,2}\s*x\b|parcela|sem\s+juros/i.test(context)) continue;

            const amount = amountFromElement(element);
            if (amount !== null) return amount;
          }
        }

        const fraction = document.querySelector(
          ".andes-money-amount__fraction, [data-andes-money-amount-fraction='true']",
        );
        const container = fraction?.closest(".andes-money-amount") || fraction?.parentElement;
        return amountFromElement(container);
      },
    });

    const price = Number(execution?.result);
    if (!Number.isFinite(price) || price <= 0 || price > 100000000) return null;
    return Math.round(price * 100) / 100;
  } catch {
    return null;
  }
}

function revealManualPrice(message) {
  els.manualPriceBox.classList.remove("hidden");
  els.send.textContent = "Enviar com preço informado";
  showResult(
    message || "Informe o preço do anúncio para continuar.",
    "warning",
  );
  setTimeout(() => els.manualPrice.focus(), 0);
}

function resetManualPrice() {
  els.manualPriceBox.classList.add("hidden");
  els.manualPrice.value = "";
  els.send.textContent = "Enviar para Criabyte";
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
  const manualPriceRequired = !els.manualPriceBox.classList.contains("hidden");
  const manualPrice = manualPriceRequired
    ? parseBrlPrice(els.manualPrice.value)
    : null;

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
  if (manualPriceRequired && manualPrice === null) {
    showResult("Informe um preço válido, por exemplo: 1.999,90.", "warning");
    els.manualPrice.focus();
    return;
  }

  await chrome.storage.local.set({ apiUrl, apiKey });

  els.send.disabled = true;
  els.send.textContent = "Enviando...";
  showResult("Analisando produto e verificando o Criabyte...", "success");

  try {
    const pagePrice = manualPrice === null
      ? await extractPriceFromCurrentTab()
      : null;
    const priceToSend = manualPrice ?? pagePrice;

    const response = await fetch(`${apiUrl}/extensao/importar-oferta`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify({
        urlProduto: productUrl,
        urlAfiliada: affiliateUrl,
        ...(priceToSend !== null ? { precoManual: priceToSend } : {}),
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
      if (
        response.status === 422 &&
        detail?.codigo === "PRECO_NAO_IDENTIFICADO"
      ) {
        revealManualPrice(
          detail?.mensagem ||
            "Preço não identificado. Informe o valor para continuar.",
        );
        return;
      }

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
    if (!warning) {
      resetManualPrice();
    }
  } catch (error) {
    showResult(
      error?.message || "Falha ao enviar a oferta para o Criabyte.",
      "error",
    );
  } finally {
    els.send.disabled = false;
    els.send.textContent = els.manualPriceBox.classList.contains("hidden")
      ? "Enviar para Criabyte"
      : "Enviar com preço informado";
  }
});

els.manualPrice?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    els.send.click();
  }
});

Promise.all([loadConfig(), loadCurrentTab()]).catch(() => {});
