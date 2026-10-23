(() => {
  const terminal = new Set(['CONCLUIDA', 'FALHOU', 'CANCELADA', 'INTERROMPIDA'])
  let polling = false
  let active = null
  const notify = operation => window.dispatchEvent(new CustomEvent('criabyte:operation', { detail: operation }))
  async function identity(key) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key))
    return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('')
  }
  async function config() {
    const stored = await chrome.storage.local.get(['apiUrl', 'apiKey'])
    return { base: String(stored.apiUrl || '').replace(/\/$/, ''), key: stored.apiKey || '' }
  }
  async function request(path, options = {}) {
    const { base, key } = await config()
    const { operation, ...fetchOptions } = options
    if (operation && (operation.base !== base || operation.owner !== await identity(key))) throw new Error('A configuração mudou. Retome o envio usando a configuração original.')
    let response
    try { response = await fetch(`${base}${path}`, { ...fetchOptions, headers: { 'Content-Type': 'application/json', 'X-API-Key': key, ...fetchOptions.headers }, signal: AbortSignal.timeout(20000) }) }
    catch (error) {
      if (['TypeError', 'TimeoutError', 'AbortError'].includes(error.name)) throw new Error('Sem conexão com o agente. Use Retomar envio quando o serviço voltar.')
      throw error
    }
    let body
    try { body = await response.json() }
    catch { const error = new Error('O agente está temporariamente indisponível. Use Retomar envio quando o serviço voltar.'); error.status = response.status; throw error }
    if (!response.ok) { const error = new Error(typeof body.detail === 'string' ? body.detail : body.detail?.mensagem || `Erro HTTP ${response.status}`); error.status = response.status; throw error }
    return body
  }
  async function poll(operation) {
    if (polling) throw new Error('Já existe uma consulta em andamento nesta janela.')
    polling = true
    active = operation
    try {
      let result
      do {
        result = await request(`/extensao/operacoes/${operation.id}`, { operation })
        notify(result)
        if (!terminal.has(result.estado)) await new Promise(resolve => setTimeout(resolve, 2000))
      } while (!terminal.has(result.estado))
      await chrome.storage.local.remove('pendingImportOperation')
      active = null
      if (result.estado !== 'CONCLUIDA') throw new Error(result.erro || 'Operação cancelada.')
      return { ...result.resultado, envio: operation.form || result.envio }
    } finally { polling = false }
  }
  async function send(body) {
    const settings = await config()
    const owner = await identity(settings.key)
    const saved = (await chrome.storage.local.get('pendingImportOperation')).pendingImportOperation
    if (saved && saved.owner === owner && saved.base === settings.base) throw new Error('Existe um envio pendente. Use Retomar antes de iniciar outro.')
    const operation = { owner, base: settings.base, requestKey: crypto.randomUUID(), form: { urlProduto: body.urlProduto, urlAfiliada: body.urlAfiliada }, body }
    await chrome.storage.local.set({ pendingImportOperation: operation })
    return start(operation)
  }
  async function start(operation) {
    if (!operation.id) {
      let result
      try { result = await request('/extensao/operacoes', { operation, method: 'POST', headers: { 'Idempotency-Key': operation.requestKey }, body: JSON.stringify(operation.body) }) } catch (error) {
        if ([400,401,403,422,429].includes(error.status)) await chrome.storage.local.remove('pendingImportOperation')
        throw error
      }
      operation = { ...operation, id: result.id }
      delete operation.body
      await chrome.storage.local.set({ pendingImportOperation: operation })
    }
    return poll(operation)
  }
  async function resume() {
    const operation = (await chrome.storage.local.get('pendingImportOperation')).pendingImportOperation
    const settings = await config()
    if (!operation || operation.owner !== await identity(settings.key) || operation.base !== settings.base) throw new Error('Nenhum envio pendente nesta configuração.')
    return start(operation)
  }
  async function cancel() {
    const operation = active || (await chrome.storage.local.get('pendingImportOperation')).pendingImportOperation
    if (!operation?.id) throw new Error('Retome o envio para consultar o estado antes de cancelar.')
    notify(await request(`/extensao/operacoes/${operation.id}/cancelar`, { operation, method: 'POST' }))
  }
  window.CriaByteOperations = { send, resume, cancel, history: () => request('/extensao/operacoes') }
})()
