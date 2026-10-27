import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'

const code = await readFile(new URL('../extension/background.js', import.meta.url), 'utf8')
const capture = code.match(/function extractProductDataFromPage\(\) \{[\s\S]*?\n\}/)?.[0]
assert.ok(capture)
function price(whole, cents, { previous = false, context = '' } = {}) {
  return {
    classList: { contains: () => previous }, parentElement: { innerText: context }, closest: () => null,
    querySelector: selector => ({ textContent: selector.includes('__fraction') ? whole : cents }),
  }
}
function row(key, value, related = false) {
  return { closest: () => related ? {} : null,
    querySelectorAll: () => [{ textContent: key }, { textContent: value }] }
}
function execute({ prices = [], rows = [], products = [] } = {}) {
  const url = new URL('https://www.mercadolivre.com.br/item-current')
  const location = { href: url.href, origin: url.origin, pathname: url.pathname, hostname: url.hostname, search: url.search }
  const document = {
    title: 'História e propaganda', body: { innerText: '' },
    querySelector: selector => selector.startsWith('h1') ? { textContent: 'SSD Kingston NV2 1 TB' } : null,
    querySelectorAll: selector => {
      if (selector === 'script[type="application/ld+json"]') return products.map(product => ({ textContent: JSON.stringify(product) }))
      if (selector === 'table tr') return rows
      if (selector.includes('andes-money-amount')) return prices
      return []
    },
  }
  return vm.runInNewContext(`(${capture})()`, { document, location, URL })
}
test('captura fração e centavos do preço atual, excluindo preço anterior e parcela', () => {
  const result = execute({ prices: [price('2.999', '90', { previous: true }), price('199', '99', { context: '12x sem juros' }), price('2.399', '90')] })
  assert.equal(result.preco, 2399.90)
})
test('usa título do produto e não mistura ficha de recomendações ou JSON-LD de outro item', () => {
  const result = execute({ rows: [row('Memória RAM', '64 GB', true), row('Capacidade', '1 TB')], products: [
    { '@type': 'Product', url: 'https://www.mercadolivre.com.br/outro-item', name: 'Outra placa', brand: 'Outra marca' },
    { '@type': 'Product', url: 'https://www.mercadolivre.com.br/item-current', name: 'Conheça a nossa história', brand: 'Kingston', model: 'NV2' },
  ] })
  assert.equal(result.nome, 'SSD Kingston NV2 1 TB')
  assert.equal(result.marca, 'Kingston')
  assert.equal(result.modelo, 'NV2')
  assert.ok(result.atributos.some(item => item.name === 'Capacidade' && item.value === '1 TB'))
  assert.ok(!result.atributos.some(item => item.value === '64 GB'))
})
test('somente parcelas ou preço anterior não viram preço à vista', () => {
  const result = execute({ prices: [price('3.000', '00', { previous: true }), price('250', '00', { context: '12x sem juros' })] })
  assert.equal(Object.hasOwn(result, 'preco'), false)
})

test('captura preserva material e compatibilidade, descartando avaliações e scripts', () => {
  const result=execute({rows:[row('Material','Plástico'),row('Compatibilidade','HP DeskJet 2136, 2676'),row('Avaliações de clientes',"4,7 var dpAcrHasRegisteredArcLinkClickAction; P.when('A')"),row('Ranking dos mais vendidos','#1'),row('Prazo','Amanhã'),row('Parcelas','10x sem juros'),row('Cor','window.ue.count("x")')]})
  assert.deepEqual(Array.from(result.atributos,item=>item.name),['Material','Compatibilidade'])
})
