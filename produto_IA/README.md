# Produto IA - CriaByte

Coletor de páginas de produto alinhado aos nomes de campos da `main` do backend CriaByte.

## Instalação

```bash
npm install
npx playwright install --with-deps chromium
```

## Uso

Detecção automática:

```bash
npm start -- "https://site.com/produto"
```

Forçando uma categoria quando necessário:

```bash
npm start -- "https://site.com/produto" TECLADO
```

## O que retorna

- categoriaDetectada
- tipoCadastro (`HARDWARE`, `PRODUTO` ou `NOTEBOOK`)
- `payloadParcialBackend` com os nomes de campos usados pelo backend
- `ofertaColetada` separada dos dados técnicos
- lista dos campos técnicos esperados para a categoria

A imagem é mantida somente como URL (`imagemUrl`). Nenhuma imagem é baixada.

## Importante

A extração técnica ainda é determinística e não inventa campos. Os schemas já espelham a `main` do backend. O próximo passo é adicionar um interpretador local/LLM para preencher melhor os campos difíceis, sempre filtrando a saída por esses schemas.
