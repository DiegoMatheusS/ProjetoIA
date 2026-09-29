let panelWindowId = null;
let lastNormalWindowId = null;

async function saveProductUrl(url) {
  if (typeof url === "string" && /^https?:/i.test(url)) {
    const saved = await chrome.storage.local.get(["lastProductUrl"]);
    if (saved.lastProductUrl && saved.lastProductUrl !== url) {
      await chrome.storage.local.remove("lastProductCapture");
    }
    await chrome.storage.local.set({ lastProductUrl: url });
    return url;
  }
  return null;
}

async function activeTabFromNormalWindow() {
  if (lastNormalWindowId !== null) {
    try {
      const tabs = await chrome.tabs.query({ active: true, windowId: lastNormalWindowId });
      if (tabs[0]?.url && /^https?:/i.test(tabs[0].url)) return tabs[0];
    } catch {
      lastNormalWindowId = null;
    }
  }

  const windows = await chrome.windows.getAll({ populate: true, windowTypes: ["normal"] });
  const normalWindow = windows.find((item) => item.focused) || windows[0];
  return normalWindow?.tabs?.find((item) => item.active) || null;
}

function extractProductDataFromPage() {
  const clean = (value) => {
    if (value === null || value === undefined) return null;
    const text = String(value).replace(/\s+/g, " ").trim();
    return text || null;
  };

  const meta = (...selectors) => {
    for (const selector of selectors) {
      const value = document.querySelector(selector)?.getAttribute("content");
      if (clean(value)) return clean(value);
    }
    return null;
  };

  const itemprop = (...names) => {
    for (const name of names) {
      const node = document.querySelector(`[itemprop="${name}"]`);
      const value = node?.getAttribute("content") || node?.textContent;
      if (clean(value)) return clean(value);
    }
    return null;
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
    if (Array.isArray(value["@graph"])) {
      const found = findProduct(value["@graph"]);
      if (found) return found;
    }
    return null;
  };

  let product = null;
  for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      product = findProduct(JSON.parse(node.textContent || "null"));
      if (product) break;
    } catch {
      // JSON-LD inválido não deve impedir a captura dos demais campos.
    }
  }

  const brandValue = product?.brand;
  const brand = clean(
    typeof brandValue === "object" && brandValue !== null
      ? brandValue.name
      : brandValue,
  ) || itemprop("brand") || meta('meta[property="product:brand"]', 'meta[name="brand"]');

  const gtin = clean(
    product?.gtin || product?.gtin14 || product?.gtin13 || product?.gtin12 || product?.gtin8,
  ) || itemprop("gtin", "gtin14", "gtin13", "gtin12", "gtin8") ||
    meta('meta[name="gtin"]', 'meta[property="product:gtin"]');

  const model = clean(product?.model) || itemprop("model") ||
    meta('meta[name="model"]', 'meta[property="product:model"]');
  const mpn = clean(product?.mpn) || itemprop("mpn") ||
    meta('meta[name="mpn"]', 'meta[property="product:mpn"]');

  const name = clean(product?.name) || meta('meta[property="og:title"]', 'meta[name="twitter:title"]') ||
    clean(document.querySelector("h1")?.textContent) || clean(document.title);

  let offer = product?.offers;
  if (Array.isArray(offer)) offer = offer[0];
  const rawPrice = clean(offer?.price) || itemprop("price") ||
    meta('meta[property="product:price:amount"]', 'meta[itemprop="price"]');
  let preco = null;
  if (rawPrice) {
    let normalized = rawPrice.replace(/[^0-9.,]/g, "");
    const lastComma = normalized.lastIndexOf(",");
    const lastDot = normalized.lastIndexOf(".");
    if (lastComma > lastDot) normalized = normalized.replace(/\./g, "").replace(",", ".");
    else if (lastDot > lastComma) normalized = normalized.replace(/,/g, "");
    else normalized = normalized.replace(",", ".");
    const parsed = Number(normalized);
    if (Number.isFinite(parsed) && parsed > 0) preco = Math.round(parsed * 100) / 100;
  }

  const pathMatch = location.pathname.match(/\/(?:dp|gp\/product|product)\/([A-Z0-9]{10})(?:[/?]|$)/i);
  const queryAsin = new URL(location.href).searchParams.get("asin");
  const domAsin = document.querySelector("[data-asin]")?.getAttribute("data-asin");
  const asinCandidate = clean(pathMatch?.[1] || queryAsin || domAsin);
  const asin = asinCandidate && /^[A-Z0-9]{10}$/i.test(asinCandidate)
    ? asinCandidate.toUpperCase()
    : null;

  const data = {
    nome: name,
    marca: brand,
    modelo: model,
    mpn,
    gtin: gtin ? gtin.replace(/[^0-9A-Za-z-]/g, "") : null,
    asin,
    preco,
  };
  return Object.fromEntries(Object.entries(data).filter(([, value]) => value !== null && value !== ""));
}

async function captureProductData(tab) {
  const url = tab?.url;
  if (!tab?.id || !url || !/^https?:/i.test(url)) return null;
  await saveProductUrl(url);
  try {
    const injected = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractProductDataFromPage,
    });
    const dados = injected?.[0]?.result && typeof injected[0].result === "object"
      ? injected[0].result
      : {};
    const capture = { url, dados, capturadoEm: Date.now() };
    await chrome.storage.local.set({ lastProductCapture: capture });
    return capture;
  } catch {
    const saved = await chrome.storage.local.get(["lastProductCapture"]);
    if (saved.lastProductCapture?.url === url) return saved.lastProductCapture;
    return { url, dados: {} };
  }
}

async function findExistingPanel() {
  const panelUrl = chrome.runtime.getURL("popup.html");
  const windows = await chrome.windows.getAll({ populate: true });
  return windows.find((win) => win.tabs?.some((item) => item.url === panelUrl)) || null;
}

chrome.action.onClicked.addListener(async (tab) => {
  if (tab?.windowId !== undefined) lastNormalWindowId = tab.windowId;
  await captureProductData(tab);

  if (panelWindowId !== null) {
    try {
      await chrome.windows.update(panelWindowId, { focused: true });
      return;
    } catch {
      panelWindowId = null;
    }
  }

  const existing = await findExistingPanel();
  if (existing?.id !== undefined) {
    panelWindowId = existing.id;
    await chrome.windows.update(existing.id, { focused: true });
    return;
  }

  const created = await chrome.windows.create({
    url: chrome.runtime.getURL("popup.html"),
    type: "popup",
    width: 520,
    height: 720,
    focused: true,
  });
  panelWindowId = created.id ?? null;
});

chrome.windows.onRemoved.addListener((windowId) => {
  if (windowId === panelWindowId) panelWindowId = null;
  if (windowId === lastNormalWindowId) lastNormalWindowId = null;
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE || windowId === panelWindowId) return;
  try {
    const win = await chrome.windows.get(windowId);
    if (win.type !== "normal") return;
    lastNormalWindowId = windowId;
    const tab = await activeTabFromNormalWindow();
    await saveProductUrl(tab?.url);
  } catch {
    // A janela pode ter sido fechada entre os eventos.
  }
});

chrome.tabs.onActivated.addListener(async ({ windowId }) => {
  try {
    const win = await chrome.windows.get(windowId);
    if (win.type !== "normal") return;
    lastNormalWindowId = windowId;
    const tab = await activeTabFromNormalWindow();
    await saveProductUrl(tab?.url);
  } catch {
    // Ignora tabs/janelas encerradas durante a troca.
  }
});

chrome.tabs.onUpdated.addListener(async (_tabId, changeInfo, tab) => {
  if (!changeInfo.url && changeInfo.status !== "complete") return;
  if (tab.windowId !== lastNormalWindowId || !tab.active) return;
  await saveProductUrl(tab.url);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "GET_CURRENT_PRODUCT_URL") {
    activeTabFromNormalWindow()
      .then(async (tab) => {
        const url = await saveProductUrl(tab?.url);
        sendResponse({ url });
      })
      .catch(() => sendResponse({ url: null }));
    return true;
  }

  if (message?.type === "GET_CURRENT_PRODUCT_DATA") {
    activeTabFromNormalWindow()
      .then(captureProductData)
      .then((capture) => sendResponse(capture || { url: null, dados: {} }))
      .catch(() => sendResponse({ url: null, dados: {} }));
    return true;
  }

  return false;
});
