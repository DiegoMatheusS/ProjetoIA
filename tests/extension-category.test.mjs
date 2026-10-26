import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

test('categoria ausente pede seleção; a escolha segue no envio e na retomada', async () => {
 const nodes = new Map(), sent = []
 function node(id) {
  if (!nodes.has(id)) nodes.set(id, { value: '', required: false, disabled: false, textContent: '', className: '', innerHTML: '', handlers: {}, dataset: {}, classList: { contains: () => true, add() {}, remove() {} }, addEventListener(name, fn) { (this.handlers[name] ||= []).push(fn) }, focus() {}, appendChild() {}, append() {}, replaceChildren() {}, querySelector() { return null } })
  return nodes.get(id)
 }
 const context = vm.createContext({ URL, Intl, console, setTimeout: fn => fn(), CSS: { escape: x => x }, document: { querySelector: id => node(id), getElementById: id => node('#'+id), createElement: () => node(Symbol()) }, window: { addEventListener() {}, CriaByteOperations: {} }, chrome: { runtime: { sendMessage: async () => ({url:'https://loja.example/item'}) }, storage: { local: { get: async () => ({apiUrl:'https://agent.example',apiKey:'test-key'}), set: async () => {} } } }, fetch: async (url, init) => { sent.push(JSON.parse(init.body)); return { ok:true, json: async () => ({status:'REVISAO_NECESSARIA', solicitarCategoria:true, motivo:'Selecione a categoria'}) } } })
 vm.runInContext(readFileSync(new URL('../extension/popup.js', import.meta.url),'utf8'), context)
 await new Promise(resolve => setImmediate(resolve))
 node('#affiliateUrl').value='https://loja.example/affiliate'
 const send=()=>node('#send').handlers.click[0]()
 await send()
 assert.equal(node('#category').required,true)
 await send()
 assert.equal(sent.length,1)
 node('#category').value='MEMORIA_RAM'
 await send()
 assert.equal(sent[1].categoria,'MEMORIA_RAM')
 vm.runInContext('applyOperationResult({status:"REVISAO_NECESSARIA", envio:{urlProduto:"https://loja.example/item",categoria:"PLACA_VIDEO"}, camposFaltantes:[]})',context)
 assert.equal(node('#category').value,'PLACA_VIDEO')
 node('#productUrl').handlers.input[0]()
 assert.equal(node('#category').value,'')
 assert.equal(node('#category').required,false)
})
