# Produto IA v14.3 - Railway

## Deploy

1. Suba esta pasta em um repositório GitHub.
2. Na Railway: New Project -> Deploy from GitHub repo.
3. Se o repositório tiver a pasta `produto_IA`, configure **Root Directory** para `/produto_IA`.
4. Railway detectará o `Dockerfile`.
5. Aguarde o deploy ficar `Active`.
6. Em Settings -> Networking -> Public Networking, clique **Generate Domain**.
7. Teste: `https://SEU-DOMINIO/health`.

## Variables recomendadas no serviço Produto IA

```env
HEADLESS=true
PRODUTO_IA_CONCURRENCY=1
PRODUTO_IA_API_KEY=COLOQUE_UMA_CHAVE_FORTE_AQUI
PRODUTO_IA_DOCS=false
ENRICHMENT_AUTO=false
CRIABYTE_API_URL=https://api.criabyte.com.br/api
```

A API key é opcional, mas recomendada. Se definida, `POST /analisar` exige:

`X-API-Key: mesma-chave`

## Endpoints

- `GET /health`
- `POST /analisar`

Exemplo de corpo:

```json
{
  "url": "https://www.magazinevoce.com.br/...",
  "categoria": null,
  "enrich": false,
  "criabytePlan": false,
  "noBrowser": false
}
```

## Backend

Depois de gerar o domínio da IA, configure no backend algo como:

```env
PRODUTO_IA_URL=https://seu-servico.up.railway.app
PRODUTO_IA_API_KEY=mesma-chave
```

O backend deve chamar `POST ${PRODUTO_IA_URL}/analisar`.
