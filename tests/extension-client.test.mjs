import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { webcrypto } from 'node:crypto'

const source = await readFile(new URL('../extension/operations-client.js', import.meta.url), 'utf8')
function client(store, fetch) {
  const window = new EventTarget()
  const storage = {
    async get(keys) { return Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map(key => [key, structuredClone(store[key])])) },
    async set(values) { Object.assign(store, structuredClone(values)) },
    async remove(key) { delete store[key] },
  }
  vm.runInNewContext(source, { window, chrome: { storage: { local: storage } }, fetch, crypto: webcrypto, TextEncoder, CustomEvent, AbortSignal, setTimeout })
  return window.CriaByteOperations
}
const settings = () => ({ apiUrl: 'https://agent.example', apiKey: 'cbext_this-device' })
const body = { urlProduto: 'https://shop.example/pc', urlAfiliada: 'https://shop.example/ref/pc' }
const response = data => ({ ok: true, json: async () => data })

test('fechar após aceitar a criação retoma com a mesma chave e não duplica a importação', async () => {
  const store = settings(), keys = new Set()
  let attempts = 0
  const fetch = async (url, options) => {
    assert.equal(options.headers['X-API-Key'], store.apiKey)
    if (options.method === 'POST') {
      attempts++
      keys.add(options.headers['Idempotency-Key'])
      if (attempts === 1) throw new Error('Janela encerrada antes da resposta')
      return response({ id: 'operation-1' })
    }
    assert.ok(url.endsWith('/operation-1'))
    return response({ estado: 'CONCLUIDA', resultado: { status: 'BUILD_E_OFERTA_CRIADOS' } })
  }
  await assert.rejects(client(store, fetch).send(body), /encerrada/)
  assert.ok(store.pendingImportOperation.requestKey)
  const result = await client(store, fetch).resume()
  assert.equal(result.status, 'BUILD_E_OFERTA_CRIADOS')
  assert.equal(result.envio.urlProduto, body.urlProduto)
  assert.equal(result.envio.urlAfiliada, body.urlAfiliada)
  assert.equal(keys.size, 1)
  assert.equal(store.pendingImportOperation, undefined)
})

test('uma operação aceita retoma apenas a consulta, sem reenviar o anúncio', async () => {
  const store = settings()
  let posts = 0, disconnected = true
  const fetch = async (_, options) => {
    if (options.method === 'POST') { posts++; return response({ id: 'operation-2' }) }
    if (disconnected) throw new Error('Sem rede')
    return response({ estado: 'CONCLUIDA', resultado: { status: 'OFERTA_ATUALIZADA' } })
  }
  await assert.rejects(client(store, fetch).send(body), /rede/)
  assert.equal(store.pendingImportOperation.id, 'operation-2')
  assert.equal(store.pendingImportOperation.body, undefined)
  disconnected = false
  assert.equal((await client(store, fetch).resume()).status, 'OFERTA_ATUALIZADA')
  assert.equal(posts, 1)
})

test('trocar a chave não consulta uma operação de outro dispositivo', async () => {
  const store = settings()
  const operations = client(store, async () => { throw new Error('Sem rede') })
  await assert.rejects(operations.send(body))
  store.apiKey = 'cbext_another-device'
  await assert.rejects(client(store, () => { throw new Error('Não deveria consultar') }).resume(), /Nenhum envio pendente/)
})

test('dados recusados liberam um novo envio, sem manter uma operação impossível de retomar', async () => {
  const store = settings()
  await assert.rejects(client(store, async () => ({ ok: false, status: 422, json: async () => ({ detail: 'Dados inválidos' }) })).send(body), /inválidos/)
  assert.equal(store.pendingImportOperation, undefined)
})

test('indisponibilidade com HTML preserva o envio para retomar quando o serviço voltar', async () => {
  const store = settings()
  const unavailable = client(store, async () => ({ status: 502, ok: false, json: async () => { throw new SyntaxError('HTML do proxy') } }))
  await assert.rejects(unavailable.send(body), /temporariamente indisponível/)
  const key = store.pendingImportOperation.requestKey
  const restored = client(store, async (_, options) => {
    if (options.method === 'POST') { assert.equal(options.headers['Idempotency-Key'], key); return response({ id: 'restored' }) }
    return response({ estado: 'CONCLUIDA', resultado: { status: 'BUILD_E_OFERTA_CRIADOS' } })
  })
  assert.equal((await restored.resume()).status, 'BUILD_E_OFERTA_CRIADOS')
})
