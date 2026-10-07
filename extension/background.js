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

  const amazon = /(^|\.)amazon\.(?:com\.br|com)$/i.test(location.hostname);
  const amazonTableValue = (...labels) => {
    if (!amazon) return null;
    const wanted = labels.map((label) => label.toLowerCase());
    const rows = document.querySelectorAll(
      "#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr, #detailBullets_feature_div li",
    );
    for (const row of rows) {
      const key = clean(row.querySelector("th, .a-text-bold")?.textContent)?.replace(/[:：]+$/, "").toLowerCase();
      if (!key || !wanted.some((label) => key === label)) continue;
      const value = clean(row.querySelector("td")?.textContent) || clean(row.textContent?.replace(row.querySelector("th, .a-text-bold")?.textContent || "", ""));
      if (value) return value;
    }
    return null;
  };

  const amazonAttributes = [];
  if (amazon) {
    const seenAttributes = new Set();
    const addAttribute = (name, value) => {
      const key = clean(name)?.replace(/[:：]+$/, "");
      const val = clean(value);
      if (!key || !val || key.length > 160 || val.length > 1000) return;
      const signature = `${key.toLowerCase()}::${val.toLowerCase()}`;
      if (seenAttributes.has(signature)) return;
      seenAttributes.add(signature);
      amazonAttributes.push({ name: key, value: val });
    };

    const additional = product?.additionalProperty || product?.additionalProperties || [];
    for (const item of Array.isArray(additional) ? additional : [additional]) {
      if (!item || typeof item !== "object") continue;
      addAttribute(item.name, typeof item.value === "object" ? item.value?.value : item.value);
    }

    const rows = document.querySelectorAll(
      "#productDetails_techSpec_section_1 tr, #productDetails_techSpec_section_2 tr, " +
      "#productDetails_detailBullets_sections1 tr, #productDetails_detailBullets_sections2 tr, " +
      "#technicalSpecifications_section_1 tr, #technicalSpecifications_section_2 tr",
    );
    for (const row of rows) {
      const keyNode = row.querySelector("th, td:first-child");
      const valueNode = row.querySelector("td:last-child");
      if (keyNode && valueNode && keyNode !== valueNode) {
        addAttribute(keyNode.textContent, valueNode.textContent);
      }
      if (amazonAttributes.length >= 160) break;
    }

    if (amazonAttributes.length < 160) {
      for (const item of document.querySelectorAll("#detailBullets_feature_div li")) {
        const keyNode = item.querySelector(".a-text-bold");
        if (!keyNode) continue;
        const key = clean(keyNode.textContent);
        const full = clean(item.textContent);
        addAttribute(key, full && key ? full.replace(key, "").trim() : full);
        if (amazonAttributes.length >= 160) break;
      }
    }
  }

  const amazonFeatureBullets = amazon
    ? Array.from(document.querySelectorAll("#feature-bullets li span.a-list-item"))
        .map((node) => clean(node.textContent))
        .filter(Boolean)
        .slice(0, 30)
    : [];
  const amazonDescription = amazon
    ? clean(document.querySelector("#productDescription")?.textContent) ||
      clean(amazonFeatureBullets.join(" | "))
    : null;
  const amazonImage = amazon
    ? clean(document.querySelector("#landingImage, #imgBlkFront")?.getAttribute("data-old-hires")) ||
      clean(document.querySelector("#landingImage, #imgBlkFront")?.getAttribute("src"))
    : null;

  const brandValue = product?.brand;
  const amazonByline = amazon ? clean(document.querySelector("#bylineInfo")?.textContent) : null;
  const brand = clean(
    typeof brandValue === "object" && brandValue !== null
      ? brandValue.name
      : brandValue,
  ) || itemprop("brand") || amazonTableValue("marca", "brand", "fabricante") ||
    (amazonByline ? amazonByline.replace(/^(?:visite a loja (?:da?|do) |marca:\s*|brand:\s*)/i, "").trim() : null) ||
    meta('meta[property="product:brand"]', 'meta[name="brand"]');

  const gtin = clean(
    product?.gtin || product?.gtin14 || product?.gtin13 || product?.gtin12 || product?.gtin8,
  ) || itemprop("gtin", "gtin14", "gtin13", "gtin12", "gtin8") ||
    amazonTableValue("ean", "gtin", "código de barras") ||
    meta('meta[name="gtin"]', 'meta[property="product:gtin"]');

  const model = clean(product?.model) || itemprop("model") ||
    amazonTableValue("número do modelo", "número do modelo do item", "modelo", "model number") ||
    meta('meta[name="model"]', 'meta[property="product:model"]');
  const mpn = clean(product?.mpn) || itemprop("mpn") ||
    amazonTableValue("número da peça", "referência do fabricante", "manufacturer part number", "mpn") ||
    meta('meta[name="mpn"]', 'meta[property="product:mpn"]');

  const name = (amazon ? clean(document.querySelector("#productTitle")?.textContent) : null) ||
    clean(product?.name) || meta('meta[property="og:title"]', 'meta[name="twitter:title"]') ||
    clean(document.querySelector("h1")?.textContent) || clean(document.title);

  let offer = product?.offers;
  if (Array.isArray(offer)) offer = offer[0];
  const amazonPrice = amazon ? clean(
    document.querySelector(
      "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen, " +
      "#corePrice_feature_div .priceToPay .a-offscreen, " +
      "#apex_desktop .priceToPay .a-offscreen, " +
      "#price_inside_buybox, #priceblock_ourprice, #priceblock_dealprice",
    )?.textContent,
  ) : null;
  const rawPrice = amazonPrice || clean(offer?.price) || itemprop("price") ||
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

  const pathMatch = location.pathname.match(/\/(?:dp|gp\/(?:aw\/d|product)|product)\/([A-Z0-9]{10})(?:[/?]|$)/i);
  const queryAsin = new URL(location.href).searchParams.get("asin");
  const domAsin = amazon
    ? document.querySelector("input#ASIN, input[name='ASIN'], input#twister-plus-asin")?.value || document.querySelector("#ASIN")?.getAttribute("value")
    : document.querySelector("[data-asin]")?.getAttribute("data-asin");
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
    descricao: amazonDescription,
    imagemUrl: amazonImage,
    atributos: amazonAttributes,
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
