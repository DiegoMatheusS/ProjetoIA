# Produto AI Starter

Projeto inicial para coletar dados de uma página de produto.

## Requisitos

- Node.js 18 ou superior

## Instalação

```bash
npm install
npx playwright install chromium
```

## Uso

```bash
npm start -- "https://site.com/produto"
```

## Saída

O programa tenta retornar:

- nome
- marca
- SKU/MPN
- preço
- moeda
- disponibilidade
- imagem
- descrição
- URL

A extração usa primeiro JSON-LD e metadados da página e depois tenta seletores genéricos.

## Próximo passo

Criar extratores específicos para cada loja e, depois, adicionar um modelo local para interpretar especificações técnicas.
