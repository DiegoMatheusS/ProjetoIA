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
  missingFieldsBox: document.querySelector("#missingFieldsBox"),
  missingFields: document.querySelector("#missingFields"),
  result: document.querySelector("#result"),
  previewBox: document.querySelector("#previewBox"),
  previewContent: document.querySelector("#previewContent"),
};

let pendingMissingFields = [];

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

function updateSendLabel() {
  if (pendingMissingFields.length) {
    els.send.textContent = "Completar e cadastrar";
    return;
  }
  if (!els.manualPriceBox.classList.contains("hidden")) {
    els.send.textContent = "Enviar com preço informado";
    return;
  }
  els.send.textContent = "Enviar para Criabyte";
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

function revealManualPrice(message) {
  els.manualPriceBox.classList.remove("hidden");
  showResult(
    message || "Informe o preço do anúncio para continuar.",
    "warning",
  );
  updateSendLabel();
  setTimeout(() => els.manualPrice.focus(), 0);
}

function resetManualPrice() {
  els.manualPriceBox.classList.add("hidden");
  els.manualPrice.value = "";
  updateSendLabel();
}

function clearMissingFields() {
  pendingMissingFields = [];
  els.missingFields.innerHTML = "";
  els.missingFieldsBox.classList.add("hidden");
  updateSendLabel();
}

function makeMissingFieldControl(field) {
  const wrapper = document.createElement("div");
  wrapper.className = "missing-field";

  const label = document.createElement("label");
  label.textContent = field.label || field.campo;
  const id = `missing-${field.campo.replace(/[^a-z0-9_-]+/gi, "-")}`;
  label.htmlFor = id;
  wrapper.appendChild(label);

  let control;
  if (Array.isArray(field.opcoes) && field.opcoes.length) {
    control = document.createElement("select");
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Selecione";
    control.appendChild(placeholder);
    for (const optionValue of field.opcoes) {
      const option = document.createElement("option");
      option.value = String(optionValue);
      option.textContent = String(optionValue);
      control.appendChild(option);
    }
  } else if (field.tipo === "boolean") {
    control = document.createElement("select");
    for (const [value, text] of [["", "Selecione"], ["true", "Sim"], ["false", "Não"]]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      control.appendChild(option);
    }
  } else {
    control = document.createElement("input");
    if (field.tipo === "integer" || field.tipo === "number") {
      control.type = "number";
      control.step = field.tipo === "integer" ? "1" : "any";
      control.inputMode = "decimal";
    } else {
      control.type = "text";
      control.autocomplete = "off";
    }
  }

  control.id = id;
  control.dataset.field = field.campo;
  control.dataset.valueType = field.tipo || "text";
  wrapper.appendChild(control);

  if (field.campo.includes(".")) {
    const hint = document.createElement("div");
    hint.className = "missing-field-hint";
    hint.textContent = "Dado técnico necessário para concluir o cadastro.";
    wrapper.appendChild(hint);
  }

  return wrapper;
}

function renderMissingFields(fields) {
  const safeFields = Array.isArray(fields)
    ? fields.filter((field) => field && field.campo)
    : [];

  pendingMissingFields = safeFields;
  els.missingFields.innerHTML = "";

  if (!safeFields.length) {
    els.missingFieldsBox.classList.add("hidden");
    updateSendLabel();
    return;
  }

  for (const field of safeFields) {
    els.missingFields.appendChild(makeMissingFieldControl(field));
  }
  els.missingFieldsBox.classList.remove("hidden");
  updateSendLabel();

  const first = els.missingFields.querySelector("input, select");
  setTimeout(() => first?.focus(), 0);
}

function collectManualFields() {
  if (!pendingMissingFields.length) return {};

  const result = {};
  for (const field of pendingMissingFields) {
    const control = els.missingFields.querySelector(
      `[data-field="${CSS.escape(field.campo)}"]`,
    );
    const raw = String(control?.value ?? "").trim();
    if (!raw) {
      showResult(`Preencha: ${field.label || field.campo}.`, "warning");
      control?.focus();
      return null;
    }

    let value = raw;
    if (field.tipo === "boolean") {
      value = raw === "true";
    } else if (field.tipo === "integer") {
      const parsed = Number(raw);
      if (!Number.isInteger(parsed)) {
        showResult(`${field.label || field.campo} precisa ser um número inteiro.`, "warning");
        control?.focus();
        return null;
      }
      value = parsed;
    } else if (field.tipo === "number") {
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) {
        showResult(`${field.label || field.campo} precisa ser um número válido.`, "warning");
        control?.focus();
        return null;
      }
      value = parsed;
    }

    result[field.campo] = value;
  }
  return result;
}

function formatBrl(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value ?? "");
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(number);
}

function humanizeKey(value) {
  return String(value || "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

function displayValue(value) {
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function appendPreviewRow(parent, key, value) {
  if (value === null || value === undefined || value === "") return;
  const row = document.createElement("div");
  row.className = "preview-row";

  const keyEl = document.createElement("div");
  keyEl.className = "preview-key";
  keyEl.textContent = key;

  const valueEl = document.createElement("div");
  valueEl.className = "preview-value";
  valueEl.textContent = displayValue(value);

  row.append(keyEl, valueEl);
  parent.appendChild(row);
}

function renderPreview(preview) {
  els.previewContent.innerHTML = "";
  if (!preview || typeof preview !== "object") {
    els.previewBox.classList.add("hidden");
    return;
  }

  appendPreviewRow(els.previewContent, "Nome", preview.nome);
  appendPreviewRow(els.previewContent, "Categoria", preview.categoria);
  appendPreviewRow(els.previewContent, "Tipo", preview.tipoCadastro);
  appendPreviewRow(els.previewContent, "Marca", preview.marca);
  appendPreviewRow(els.previewContent, "Modelo", preview.modelo);
  appendPreviewRow(els.previewContent, "Preço", preview.preco !== null && preview.preco !== undefined ? formatBrl(preview.preco) : null);
  appendPreviewRow(els.previewContent, "Preço anterior", preview.precoAnterior !== null && preview.precoAnterior !== undefined ? formatBrl(preview.precoAnterior) : null);
  appendPreviewRow(els.previewContent, "Parceiro", preview.parceiro);
  if (preview.publicado !== null && preview.publicado !== undefined) {
    appendPreviewRow(els.previewContent, "Publicado", preview.publicado ? "Sim" : "Não");
  }

  const specs = preview.especificacoes;
  if (specs && typeof specs === "object" && Object.keys(specs).length) {
    const block = document.createElement("div");
    block.className = "preview-specs";
    const title = document.createElement("div");
    title.className = "preview-specs-title";
    title.textContent = "Especificações encontradas";
    block.appendChild(title);
    for (const [key, value] of Object.entries(specs)) {
      appendPreviewRow(block, humanizeKey(key), value);
    }
    els.previewContent.appendChild(block);
  }

  els.previewBox.classList.remove("hidden");
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
  const itemName = data?.produto?.nome || data?.hardware?.nome || "";
  const item = itemName ? ` — ${itemName}` : "";
  const partner = data?.parceiro?.nome ? ` (${data.parceiro.nome})` : "";

  switch (data?.status) {
    case "OFERTA_ATUALIZADA":
      return `Oferta existente atualizada${item}${partner}.`;
    case "NOVA_OFERTA_CRIADA":
      return `Nova oferta adicionada${item}${partner}.`;
    case "PRODUTO_E_OFERTA_CRIADOS":
      return `Produto cadastrado, publicado e oferta criada${item}${partner}.`;
    case "HARDWARE_E_OFERTA_CRIADOS":
      return `Hardware cadastrado, produto publicado e oferta criada${item}${partner}.`;
    case "REVISAO_NECESSARIA":
      return data?.motivo || "O produto precisa de dados adicionais antes do cadastro.";
    default:
      return "Operação concluída.";
  }
}

els.currentTab.addEventListener("click", async () => {
  await loadCurrentTab();
  if (els.productUrl.value) {
    clearMissingFields();
    renderPreview(null);
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
  const manualFields = collectManualFields();

  if (manualFields === null) return;

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
    const response = await fetch(`${apiUrl}/extensao/importar-oferta`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify({
        urlProduto: productUrl,
        urlAfiliada: affiliateUrl,
        ...(manualPrice !== null ? { precoManual: manualPrice } : {}),
        ...(Object.keys(manualFields).length ? { dadosManuais: manualFields } : {}),
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

    renderPreview(data?.previa);

    const warning = data?.status === "REVISAO_NECESSARIA";
    if (warning) {
      renderMissingFields(data?.camposFaltantes);
      showResult(resultMessage(data), "warning");
      return;
    }

    showResult(resultMessage(data), "success");
    clearMissingFields();
    resetManualPrice();
  } catch (error) {
    showResult(
      error?.message || "Falha ao enviar a oferta para o Criabyte.",
      "error",
    );
  } finally {
    els.send.disabled = false;
    updateSendLabel();
  }
});

els.manualPrice?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    els.send.click();
  }
});

els.missingFields?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.target?.tagName !== "SELECT") {
    event.preventDefault();
    els.send.click();
  }
});

Promise.all([loadConfig(), loadCurrentTab()]).catch(() => {});
