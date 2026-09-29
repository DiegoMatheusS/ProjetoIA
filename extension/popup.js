const DEFAULT_API_URL = "https://projetoia-production.up.railway.app";

const els = {
  productUrl: document.querySelector("#productUrl"),
  affiliateUrl: document.querySelector("#affiliateUrl"),
  apiUrl: document.querySelector("#apiUrl"),
  apiKey: document.querySelector("#apiKey"),
  currentTab: document.querySelector("#currentTab"),
  pasteAffiliate: document.querySelector("#pasteAffiliate"),
  send: document.querySelector("#send"),
  confirm: document.querySelector("#confirm"),
  saveConfig: document.querySelector("#saveConfig"),
  pinAlwaysOnTop: document.querySelector("#pinAlwaysOnTop"),
  manualPriceBox: document.querySelector("#manualPriceBox"),
  manualPrice: document.querySelector("#manualPrice"),
  missingFieldsBox: document.querySelector("#missingFieldsBox"),
  missingFields: document.querySelector("#missingFields"),
  aiActionsBox: document.querySelector("#aiActionsBox"),
  completeOpenAI: document.querySelector("#completeOpenAI"),
  completeMetaAI: document.querySelector("#completeMetaAI"),
  result: document.querySelector("#result"),
  previewBox: document.querySelector("#previewBox"),
  previewContent: document.querySelector("#previewContent"),
  capturedBox: document.querySelector("#capturedBox"),
  capturedContent: document.querySelector("#capturedContent"),
};

let activeProductTabId = null;
let capturedPageData = {};
let capturedPageUrl = null;
let pendingMissingFields = [];
let preparationToken = null;

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
    if (dots === 1 && text.length - text.lastIndexOf(".") - 1 === 3) {
      text = text.replace(".", "");
    } else if (dots > 1) {
      text = text.replace(/\./g, "");
    }
  }
  const parsed = Number(text);
  if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 100000000) return null;
  return Math.round(parsed * 100) / 100;
}

function formatBrl(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value ?? "");
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(number);
}

function displayValue(value) {
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

function humanizeKey(value) {
  return String(value || "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

function appendInfoRow(parent, key, value, prefix = "preview") {
  if (value === null || value === undefined || value === "") return;
  const row = document.createElement("div");
  row.className = `${prefix}-row`;
  const keyEl = document.createElement("div");
  keyEl.className = `${prefix}-key`;
  keyEl.textContent = key;
  const valueEl = document.createElement("div");
  valueEl.className = `${prefix}-value`;
  valueEl.textContent = displayValue(value);
  row.append(keyEl, valueEl);
  parent.appendChild(row);
}

function renderCaptured(data) {
  els.capturedContent.innerHTML = "";
  const keys = [
    ["Nome", data?.nome],
    ["Marca", data?.marca],
    ["Modelo", data?.modelo],
    ["ASIN", data?.asin],
    ["GTIN", data?.gtin],
    ["MPN", data?.mpn],
    ["Preço", data?.preco ? formatBrl(data.preco) : null],
  ];
  for (const [key, value] of keys) appendInfoRow(els.capturedContent, key, value, "captured");
  const hasData = keys.some(([, value]) => value !== null && value !== undefined && value !== "");
  els.capturedBox.classList.toggle("hidden", !hasData);
}

function renderPreview(preview) {
  els.previewContent.innerHTML = "";
  if (!preview || typeof preview !== "object") {
    els.previewBox.classList.add("hidden");
    return;
  }

  appendInfoRow(els.previewContent, "Ação", preview.acao === "SOMENTE_OFERTA" ? "Adicionar somente oferta" : "Criar item + oferta");
  appendInfoRow(els.previewContent, "Nome", preview.nome);
  appendInfoRow(els.previewContent, "Categoria", preview.categoria);
  appendInfoRow(els.previewContent, "Tipo", preview.tipoCadastro);
  appendInfoRow(els.previewContent, "Marca", preview.marca);
  appendInfoRow(els.previewContent, "Modelo", preview.modelo);
  appendInfoRow(els.previewContent, "ASIN", preview.asin);
  appendInfoRow(els.previewContent, "GTIN", preview.gtin);
  appendInfoRow(els.previewContent, "MPN", preview.mpn);
  appendInfoRow(els.previewContent, "Preço", preview.preco != null ? formatBrl(preview.preco) : null);
  appendInfoRow(els.previewContent, "Fornecedor", preview.fornecedor || preview.parceiro);
  appendInfoRow(els.previewContent, "Já cadastrado", preview.existente === true ? "Sim" : preview.existente === false ? "Não" : null);
  appendInfoRow(els.previewContent, "Correspondência", preview.criterioCorrespondencia);
  appendInfoRow(els.previewContent, "Publicar", preview.publicar ? "Sim" : null);

  const specs = preview.especificacoes;
  if (specs && typeof specs === "object" && Object.keys(specs).length) {
    const block = document.createElement("div");
    block.className = "preview-specs";
    const title = document.createElement("div");
    title.className = "preview-specs-title";
    title.textContent = "Especificações encontradas";
    block.appendChild(title);
    for (const [key, value] of Object.entries(specs)) {
      appendInfoRow(block, humanizeKey(key), value);
    }
    els.previewContent.appendChild(block);
  }
  els.previewBox.classList.remove("hidden");
}

function revealManualPrice(message) {
  els.manualPriceBox.classList.remove("hidden");
  showResult(message || "Informe o preço do anúncio para continuar.", "warning");
  setTimeout(() => els.manualPrice.focus(), 0);
}

function hideManualPrice() {
  els.manualPriceBox.classList.add("hidden");
}

function clearMissingFields() {
  pendingMissingFields = [];
  els.missingFields.innerHTML = "";
  els.missingFieldsBox.classList.add("hidden");
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
  const safe = Array.isArray(fields) ? fields.filter((field) => field?.campo) : [];
  pendingMissingFields = safe;
  els.missingFields.innerHTML = "";
  if (!safe.length) {
    els.missingFieldsBox.classList.add("hidden");
    return;
  }
  for (const field of safe) els.missingFields.appendChild(makeMissingFieldControl(field));
  els.missingFieldsBox.classList.remove("hidden");
  setTimeout(() => els.missingFields.querySelector("input, select")?.focus(), 0);
}

function collectManualFields() {
  if (!pendingMissingFields.length) return {};
  const result = {};
  for (const field of pendingMissingFields) {
    const control = els.missingFields.querySelector(`[data-field="${CSS.escape(field.campo)}"]`);
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

function resetPreparedState({ keepPreview = false } = {}) {
  preparationToken = null;
  els.confirm.classList.add("hidden");
  els.aiActionsBox.classList.add("hidden");
  if (!keepPreview) els.previewBox.classList.add("hidden");
}

function captureProductDataInPage() {
  const clean = (value) => {
    if (value == null) return null;
    const text = String(value).replace(/\s+/g, " ").trim();
    return text || null;
  };
  const first = (...values) => values.map(clean).find(Boolean) || null;
  const meta = (selector) => document.querySelector(selector)?.getAttribute("content") || null;
  const text = (selector) => document.querySelector(selector)?.textContent || null;
  const parsePrice = (value) => {
    if (value == null) return null;
    let raw = String(value).replace(/[^0-9.,]/g, "");
    if (!raw) return null;
    const comma = raw.lastIndexOf(",");
    const dot = raw.lastIndexOf(".");
    if (comma > dot) raw = raw.replace(/\./g, "").replace(",", ".");
    else if (dot > comma && comma >= 0) raw = raw.replace(/,/g, "");
    else if (comma >= 0) raw = raw.replace(/\./g, "").replace(",", ".");
    const number = Number(raw);
    return Number.isFinite(number) && number > 0 ? Math.round(number * 100) / 100 : null;
  };
  const findProduct = (value) => {
    if (!value || typeof value !== "object") return null;
    if (Array.isArray(value)) {
      for (const item of value) {
        const found = findProduct(item);
        if (found) return found;
      }
      return null;
    }
    const type = value["@type"];
    if (type === "Product" || (Array.isArray(type) && type.includes("Product"))) return value;
    if (Array.isArray(value["@graph"])) return findProduct(value["@graph"]);
    return null;
  };

  let product = null;
  for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      product = findProduct(JSON.parse(script.textContent || "null"));
      if (product) break;
    } catch {
      // JSON-LD inválido de terceiros não deve impedir a captura.
    }
  }

  const brand = typeof product?.brand === "object" ? product.brand?.name : product?.brand;
  const offers = Array.isArray(product?.offers) ? product.offers[0] : product?.offers;
  const url = location.href;
  const asinUrl = /\/(?:dp|gp\/product|gp\/aw\/d)\/([A-Z0-9]{10})(?:[/?]|$)/i.exec(location.pathname)?.[1];
  const asinDom = document.querySelector("[data-asin]:not([data-asin=''])")?.getAttribute("data-asin");
  const asinInput = document.querySelector("#ASIN")?.value || document.querySelector('input[name="ASIN"]')?.value;
  const asin = first(asinUrl, asinInput, asinDom);

  const gtin = first(
    product?.gtin14,
    product?.gtin13,
    product?.gtin12,
    product?.gtin8,
    product?.gtin,
    meta('[itemprop="gtin13"]'),
    meta('[itemprop="gtin12"]'),
  );

  const price = [
    offers?.price,
    meta('[itemprop="price"]'),
    meta('meta[property="product:price:amount"]'),
    text(".a-price .a-offscreen"),
    text("[data-testid='price-part']"),
  ].map(parsePrice).find((value) => value != null) || null;

  const image = typeof product?.image === "string"
    ? product.image
    : Array.isArray(product?.image)
      ? product.image[0]
      : product?.image?.url;

  return {
    url,
    nome: first(product?.name, meta('meta[property="og:title"]'), text("h1"), document.title),
    marca: first(brand, meta('meta[itemprop="brand"]')),
    modelo: first(product?.model, meta('meta[itemprop="model"]')),
    mpn: first(product?.mpn, meta('meta[itemprop="mpn"]')),
    gtin,
    asin,
    preco: price,
    imagemUrl: first(image, meta('meta[property="og:image"]')),
  };
}

async function captureCurrentPage() {
  try {
    const response = await chrome.runtime.sendMessage({ type: "GET_CURRENT_PRODUCT_URL" });
    if (!response?.url || !/^https?:/i.test(response.url)) return null;
    activeProductTabId = response.tabId ?? null;
    els.productUrl.value = response.url;
    capturedPageUrl = response.url;

    if (activeProductTabId == null) {
      capturedPageData = {};
      renderCaptured(capturedPageData);
      return response.url;
    }

    const executions = await chrome.scripting.executeScript({
      target: { tabId: activeProductTabId },
      func: captureProductDataInPage,
    });
    capturedPageData = executions?.[0]?.result || {};
    capturedPageUrl = capturedPageData.url || response.url;
    if (capturedPageData.preco && !els.manualPrice.value) {
      hideManualPrice();
    }
    renderCaptured(capturedPageData);
    return response.url;
  } catch {
    const saved = await chrome.storage.local.get(["lastProductUrl"]);
    if (saved.lastProductUrl && /^https?:/i.test(saved.lastProductUrl)) {
      els.productUrl.value = saved.lastProductUrl;
      capturedPageUrl = saved.lastProductUrl;
      capturedPageData = {};
      renderCaptured(capturedPageData);
      return saved.lastProductUrl;
    }
    return null;
  }
}

async function loadConfig() {
  const saved = await chrome.storage.local.get(["apiUrl", "apiKey"]);
  els.apiUrl.value = saved.apiUrl || DEFAULT_API_URL;
  els.apiKey.value = saved.apiKey || "";
  if (!saved.apiUrl) await chrome.storage.local.set({ apiUrl: DEFAULT_API_URL });
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

async function apiPost(path, body) {
  const apiUrl = cleanBaseUrl(els.apiUrl.value || DEFAULT_API_URL);
  const apiKey = String(els.apiKey.value || "").trim();
  if (!isHttpUrl(apiUrl)) throw new Error("A URL da Produto IA é inválida.");
  if (!apiKey) throw new Error("Abra Configuração e informe a chave da API.");
  await chrome.storage.local.set({ apiUrl, apiKey });

  const response = await fetch(`${apiUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify(body),
  });
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.mensagem || detail?.message || data?.message || `Erro HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

function buildPrepareBody(provider = null) {
  const productUrl = String(els.productUrl.value || "").trim();
  const affiliateUrl = String(els.affiliateUrl.value || "").trim();
  if (!isHttpUrl(productUrl)) throw new Error("A página do produto é inválida.");
  if (!isHttpUrl(affiliateUrl)) throw new Error("Cole um link afiliado válido.");

  const manualPriceVisible = !els.manualPriceBox.classList.contains("hidden");
  const manualPrice = manualPriceVisible ? parseBrlPrice(els.manualPrice.value) : null;
  if (manualPriceVisible && manualPrice == null) {
    throw new Error("Informe um preço válido, por exemplo: 1.999,90.");
  }
  const manualFields = collectManualFields();
  if (manualFields === null) return null;

  const sameCapturedPage = capturedPageUrl && productUrl.split("#")[0] === String(capturedPageUrl).split("#")[0];
  return {
    urlProduto: productUrl,
    urlAfiliada: affiliateUrl,
    dadosPagina: sameCapturedPage ? capturedPageData : {},
    dadosManuais: manualFields,
    ...(manualPrice != null ? { precoManual: manualPrice } : {}),
    ...(provider ? { provedorComplemento: provider } : {}),
  };
}

function handlePreparation(data) {
  preparationToken = null;
  els.confirm.classList.add("hidden");
  els.aiActionsBox.classList.add("hidden");
  renderPreview(data?.previa);

  switch (data?.status) {
    case "PRECISA_PRECO":
      revealManualPrice(data.motivo || "Preço não identificado.");
      return;
    case "COMPLETAR_COM_IA":
      clearMissingFields();
      els.aiActionsBox.classList.remove("hidden");
      showResult("O item não existe no Criabyte. Escolha como completar a ficha técnica.", "warning");
      return;
    case "REVISAO_NECESSARIA":
      if (Array.isArray(data.camposFaltantes) && data.camposFaltantes.length) {
        renderMissingFields(data.camposFaltantes);
      }
      showResult(data.motivo || "O cadastro precisa de revisão.", "warning");
      return;
    case "PRONTO_PARA_CONFIRMAR":
      clearMissingFields();
      hideManualPrice();
      els.aiActionsBox.classList.add("hidden");
      preparationToken = data.token || null;
      if (!preparationToken) {
        showResult("A preparação não retornou token de confirmação.", "error");
        return;
      }
      els.confirm.classList.remove("hidden");
      if (data.acao === "SOMENTE_OFERTA") {
        showResult("Produto já existe no Criabyte. Revise a prévia e confirme para adicionar somente a oferta.", "success");
      } else {
        showResult("Produto não encontrado no Criabyte. Revise a prévia antes de criar e publicar.", "success");
      }
      return;
    default:
      showResult(data?.motivo || "Resposta inesperada da Produto IA.", "warning");
  }
}

async function prepareOffer(provider = null) {
  resetPreparedState({ keepPreview: false });
  let body;
  try {
    body = buildPrepareBody(provider);
    if (!body) return;
  } catch (error) {
    showResult(error.message, "warning");
    return;
  }

  const buttons = [els.send, els.completeOpenAI, els.completeMetaAI];
  buttons.forEach((button) => { if (button) button.disabled = true; });
  els.send.textContent = provider === "META_AI" ? "Completando com MetaIA..." : provider === "OPENAI" ? "Completando com IA..." : "Analisando...";
  showResult("Capturando identidade, consultando o Criabyte e preparando a prévia...", "success");

  try {
    const data = await apiPost("/extensao/preparar-oferta", body);
    handlePreparation(data);
  } catch (error) {
    showResult(error?.message || "Falha ao preparar a oferta.", "error");
  } finally {
    buttons.forEach((button) => { if (button) button.disabled = false; });
    els.send.textContent = pendingMissingFields.length ? "Reanalisar com dados preenchidos" : "Analisar e preparar";
  }
}

async function confirmOffer() {
  if (!preparationToken) {
    showResult("Prepare a oferta antes de confirmar.", "warning");
    return;
  }
  els.confirm.disabled = true;
  els.confirm.textContent = "Confirmando...";
  showResult("Gravando no Criabyte...", "success");
  try {
    const data = await apiPost("/extensao/confirmar-oferta", { token: preparationToken });
    renderPreview(data?.previa);
    const itemName = data?.produto?.nome || data?.hardware?.nome || data?.previa?.nome || "produto";
    const reused = data?.reutilizado || data?.previa?.existente;
    showResult(
      reused
        ? `Concluído: ${itemName}. O cadastro existente foi reutilizado e a oferta foi vinculada.`
        : `Concluído: ${itemName}. Produto/Hardware, oferta e publicação foram criados.`,
      "success",
    );
    preparationToken = null;
    els.confirm.classList.add("hidden");
    els.aiActionsBox.classList.add("hidden");
    clearMissingFields();
    hideManualPrice();
  } catch (error) {
    showResult(error?.message || "Falha ao confirmar o cadastro.", "error");
  } finally {
    els.confirm.disabled = false;
    els.confirm.textContent = "Confirmar cadastro";
  }
}

async function pinAlwaysOnTop() {
  if (!("documentPictureInPicture" in window)) {
    showResult("Este Chrome não oferece o modo de janela sempre sobreposta.", "warning");
    return;
  }
  try {
    const app = document.querySelector(".app");
    const sourceWindow = await chrome.windows.getCurrent();
    const pipWindow = await documentPictureInPicture.requestWindow({
      width: 520,
      height: 780,
      disallowReturnToOpener: true,
    });
    for (const styleSheet of [...document.styleSheets]) {
      try {
        const style = pipWindow.document.createElement("style");
        style.textContent = [...styleSheet.cssRules].map((rule) => rule.cssText).join("\n");
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
      try { await chrome.windows.update(sourceWindow.id, { state: "minimized" }); } catch {}
    }
    pipWindow.addEventListener("pagehide", async () => {
      if (sourceWindow?.id === undefined) return;
      try { await chrome.windows.remove(sourceWindow.id); } catch {}
    }, { once: true });
  } catch (error) {
    showResult(error?.message || "Não foi possível ativar o modo sempre sobreposto.", "warning");
  }
}

els.currentTab.addEventListener("click", async () => {
  resetPreparedState();
  const url = await captureCurrentPage();
  showResult(url ? "Página atual capturada. Confira os dados encontrados." : "Não foi possível capturar a aba atual.", url ? "success" : "warning");
});

els.pasteAffiliate.addEventListener("click", async () => {
  try {
    els.affiliateUrl.value = (await navigator.clipboard.readText()).trim();
  } catch {
    showResult("Não consegui ler a área de transferência. Cole o link manualmente.", "warning");
  }
});

els.productUrl.addEventListener("input", () => resetPreparedState());
els.affiliateUrl.addEventListener("input", () => resetPreparedState());
els.manualPrice.addEventListener("input", () => resetPreparedState({ keepPreview: true }));
els.send.addEventListener("click", () => prepareOffer());
els.confirm.addEventListener("click", confirmOffer);
els.completeOpenAI.addEventListener("click", () => prepareOffer("OPENAI"));
els.completeMetaAI.addEventListener("click", () => prepareOffer("META_AI"));
els.saveConfig.addEventListener("click", saveConfig);
els.pinAlwaysOnTop?.addEventListener("click", pinAlwaysOnTop);
els.manualPrice?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    prepareOffer();
  }
});

Promise.all([loadConfig(), captureCurrentPage()]).catch(() => {});
