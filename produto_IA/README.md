# Produto IA - CriaByte

Coletor de produtos alinhado à `main` do backend CriaByte.

## Fontes e APIs

O projeto suporta três modos:

1. lojas/fabricantes via navegador e extratores;
2. Mercado Livre via API oficial quando `ML_ACCESS_TOKEN` estiver configurado;
3. Shopee via Shopee Affiliate Open API quando `SHOPEE_AFFILIATE_APP_ID` e `SHOPEE_AFFILIATE_SECRET` estiverem configurados.

Sem credenciais, Mercado Livre e Shopee continuam podendo ser coletados pelo navegador como fallback, quando a página permitir.

A URL fornecida pelo usuário nunca é substituída como `urlOriginal`. No caso da Shopee, quando a API devolver `offerLink`, ele aparece separado como `marketplace.affiliateUrl`.

## Mercado Livre

A API usa o item ID encontrado na URL e consulta:

- `/items/{ITEM_ID}?include_attributes=all`
- `/items/{ITEM_ID}/prices`
- `/items/{ITEM_ID}/sale_price?context=channel_marketplace`

O resultado da API é usado para preço, preço anterior quando disponível, imagem, título, identificadores e atributos técnicos. O scraper continua sendo fallback.

Configure:

```text
ML_ACCESS_TOKEN=...
```

## Shopee

A integração usa a Shopee Affiliate Open API GraphQL e `productOfferV2`, quando as credenciais de afiliado estiverem disponíveis.

Configure:

```text
SHOPEE_AFFILIATE_APP_ID=...
SHOPEE_AFFILIATE_SECRET=...
```

A API pode retornar, entre outros:

- nome;
- link do produto;
- link de afiliado;
- imagem;
- preço mínimo/máximo;
- desconto;
- vendas;
- avaliação;
- comissão.

## Instalação

```bash
npm install
npx playwright install --with-deps chromium
```

## Uso

```bash
npm start -- "https://site.com/produto"
```

Categoria forçada, se necessário:

```bash
npm start -- "https://site.com/produto" TECLADO
```

## Segurança

Nunca coloque `ML_ACCESS_TOKEN`, `SHOPEE_AFFILIATE_APP_ID` ou `SHOPEE_AFFILIATE_SECRET` no Git. Use Secrets/Environment Variables do Codespaces.

## Precisão

O coletor não deve preencher um campo técnico apenas porque uma palavra apareceu na página. Ele prioriza ficha técnica e dados estruturados. Quando a API oficial fornece atributos, eles entram como fonte adicional de evidência.

A IA local ainda não é usada. Ela será adicionada depois como interpretador de casos difíceis, sempre limitada ao schema real do backend.
