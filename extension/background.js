let panelWindowId = null;
let lastNormalWindowId = null;

async function saveProductUrl(url) {
  if (typeof url === "string" && /^https?:/i.test(url)) {
    await chrome.storage.local.set({ lastProductUrl: url });
    return url;
  }
  return null;
}

async function activeTabFromNormalWindow() {
  if (lastNormalWindowId !== null) {
    try {
      const tabs = await chrome.tabs.query({
        active: true,
        windowId: lastNormalWindowId,
      });
      const url = tabs[0]?.url;
      if (url && /^https?:/i.test(url)) return url;
    } catch {
      lastNormalWindowId = null;
    }
  }

  const windows = await chrome.windows.getAll({
    populate: true,
    windowTypes: ["normal"],
  });
  const normalWindow = windows.find((item) => item.focused) || windows[0];
  const tab = normalWindow?.tabs?.find((item) => item.active);
  return tab?.url && /^https?:/i.test(tab.url) ? tab.url : null;
}

chrome.action.onClicked.addListener(async (tab) => {
  if (tab?.windowId !== undefined) {
    lastNormalWindowId = tab.windowId;
  }
  await saveProductUrl(tab?.url);

  if (panelWindowId !== null) {
    try {
      await chrome.windows.update(panelWindowId, { focused: true });
      return;
    } catch {
      panelWindowId = null;
    }
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
  if (windowId === panelWindowId) {
    panelWindowId = null;
  }
  if (windowId === lastNormalWindowId) {
    lastNormalWindowId = null;
  }
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE || windowId === panelWindowId) {
    return;
  }
  try {
    const win = await chrome.windows.get(windowId);
    if (win.type === "normal") {
      lastNormalWindowId = windowId;
      const url = await activeTabFromNormalWindow();
      await saveProductUrl(url);
    }
  } catch {
    // A janela pode ter sido fechada entre os eventos.
  }
});

chrome.tabs.onActivated.addListener(async ({ windowId }) => {
  try {
    const win = await chrome.windows.get(windowId);
    if (win.type !== "normal") return;
    lastNormalWindowId = windowId;
    const url = await activeTabFromNormalWindow();
    await saveProductUrl(url);
  } catch {
    // Ignora tabs/janelas encerradas durante a troca.
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!changeInfo.url && changeInfo.status !== "complete") return;
  if (tab.windowId !== lastNormalWindowId || !tab.active) return;
  await saveProductUrl(tab.url);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "GET_CURRENT_PRODUCT_URL") return false;

  activeTabFromNormalWindow()
    .then(async (url) => {
      if (url) await saveProductUrl(url);
      sendResponse({ url });
    })
    .catch(() => sendResponse({ url: null }));

  return true;
});
