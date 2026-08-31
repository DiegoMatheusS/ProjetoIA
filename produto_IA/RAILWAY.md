# Produto IA v14.9 - Railway

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
- `POST /analisar-captura`

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

## Surfsky v14.9

Configure no serviço `ProjetoIA` da Railway:

```env
SURFSKY_TOKEN=SEU_TOKEN
SURFSKY_API_URL=https://api-de2.surfsky.io
SURFSKY_PROXY_COUNTRY=br
```

O Surfsky é acionado somente depois das tentativas normais da Railway falharem. A v14.9 cria um perfil one-time, recebe `ws_url`, conecta o Playwright por CDP e encerra a sessão ao terminar. O token é enviado apenas no header `X-Cloud-Api-Token`.

Variáveis opcionais:

```env
# SURFSKY_PROXY_TIER=shared
# SURFSKY_PROXY_URL=
# SURFSKY_INACTIVE_KILL_TIMEOUT=90
# SURFSKY_FINGERPRINT_OS=win
```

`SURFSKY_PROXY_TIER` deve ser usado apenas se você quiser fixar explicitamente um tier habilitado na conta. Sem ele, o Surfsky escolhe o tier disponível conforme a conta.
