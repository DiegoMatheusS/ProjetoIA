# Produto IA v14.8 - Railway

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


## Coleta Magalu / Magazine Você na nuvem

A v14.6 usa, nesta ordem:

1. HTTP da URL original.
2. Chromium/Playwright da URL original.
3. Para links `magazinevoce.com.br`, página pública equivalente em `magazineluiza.com.br` por HTTP.
4. Chromium/Playwright da página pública equivalente.

Se o site devolver uma página de verificação (`az-request-verify`) em todos os caminhos, a API retorna `MAGALU_COLETA_BLOQUEADA` e **não transforma o texto da verificação em produto**. O backend deve manter a confirmação desabilitada nesse caso.

O cache foi versionado na v14.6, portanto respostas incorretas de verificação salvas pela v14.3 não são reaproveitadas.


## Fallback adicional v14.6

Para links Magazine Você bloqueados, além da página desktop do Magazine Luiza, a v14.6 tenta a mesma página sem `seller_id` e no domínio público móvel `m.magazineluiza.com.br`. Essas variações usam o mesmo código de produto. Se todas forem bloqueadas, a API continua retornando `MAGALU_COLETA_BLOQUEADA` sem criar dados falsos.

## Browserless v14.8

Para manter a coleta em nuvem quando o Magalu bloquear IPs da Railway, configure no serviço ProjetoIA:

```env
BROWSERLESS_TOKEN=SEU_TOKEN
BROWSERLESS_PROXY=residential
BROWSERLESS_PROXY_COUNTRY=BR
BROWSERLESS_PROXY_STICKY=true
BROWSERLESS_PROXY_LOCALE_MATCH=true
BROWSERLESS_STEALTH=true
```

O Browserless só é acionado depois das tentativas normais falharem. O token é lido apenas do ambiente e não é escrito nos logs/respostas.
