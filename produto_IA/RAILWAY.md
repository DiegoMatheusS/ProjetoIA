## v14.20.2 - ficha completa + busca mais rápida

- A descoberta devolve **todos os campos técnicos previstos no schema da categoria**; o que não foi confirmado fica `null`.
- `camposAusentes`, `camposObrigatoriosAusentes` e `camposEssenciaisAusentes` são recalculados a partir do schema completo.
- `fontes` volta em formato simples para o frontend (`["PC-Kombo", "CPU-Monkey"]`) e `fontesDetalhadas` mantém diagnóstico/URL.
- Enriquecimento em lote ficou seletivo: evita consultar novamente a própria fonte do candidato e prioriza as fontes mais úteis por categoria.
- Meta padrão da busca em lote: 82% de cobertura **sem faltar campos essenciais**; a ficha individual continua podendo tentar 100%.
- Timeout global padrão reduzido para 45s; detalhe por candidato 4s; enriquecimento 6s; máximo 2 fontes extras; 8 workers.
- Nenhum campo é inventado: campos não confirmados permanecem `null` e aparecem em `camposAusentes`.
- Health: `14.20.2-railway`.

# Produto IA v14.17 - Railway

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
PRODUTO_IA_API_KEY=SUA_CHAVE_PRODUTO_IA
PRODUTO_IA_DOCS=false
ENRICHMENT_AUTO=false  # opcional; v14.15 enriquece automaticamente sempre que faltar campo técnico esperado
ENRICHMENT_DISABLE=false
CRIABYTE_API_URL=https://api.criabyte.com.br/api
```

A API key é opcional, mas recomendada. Se definida, `POST /analisar` exige:

`X-API-Key: mesma-chave`

## Endpoints

- `GET /health`
- `POST /analisar`
- `POST /analisar-captura`
- `GET /descobrir-hardwares/fontes`
- `POST /descobrir-hardwares`
- `POST /descobrir-hardwares/detalhar`

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
PRODUTO_IA_API_KEY=SUA_CHAVE_PRODUTO_IA
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
SURFSKY_TOKEN=SEU_TOKEN_SURFSKY
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



## Mercado Livre v14.13

Quando a API do Mercado Livre vier parcial ou sem dados, a Produto IA usa o Surfsky já configurado para abrir a PDP real. A coleta tenta expandir características e descrição, lê o preço principal sem confundir parcelas e mescla apenas campos ausentes com os dados da API. Links `meli.la` também são reconhecidos. Não é necessária variável nova além das `SURFSKY_*` já usadas.

## Enriquecimento técnico automático v14.12

A partir da v14.12, `ENRICHMENT_AUTO=false` **não impede** o fallback necessário quando Magalu/Mercado Livre entregam uma ficha técnica incompleta. Se a identidade do produto estiver confirmada (GTIN, marca+MPN ou marca+modelo forte) e houver campos técnicos ausentes, a IA consulta automaticamente, nesta prioridade:

1. fabricante oficial;
2. CPU-World (processadores);
3. CPU-Monkey (processadores);
4. WikiChip (CPU/GPU);
5. TechPowerUp (GPU);
6. PC-Kombo;
7. Geizhals.

Somente campos ausentes são preenchidos. Valores conflitantes são registrados em `enriquecimentoTecnico.conflitos` e não substituem silenciosamente o valor principal. Para desativar completamente esse fallback, use `ENRICHMENT_DISABLE=true`.


## Descoberta de Hardwares v14.17

A descoberta é um fluxo separado de marketplace. Ela serve para a página Admin que lista Hardwares ainda não cadastrados.

Exemplo:

```json
{
  "categoria": "PROCESSADOR",
  "marca": "Intel",
  "consulta": "Core i5",
  "pagina": 1,
  "limite": 20,
  "detalhar": true,
  "enriquecer": true
}
```

O backend deve chamar `POST ${PRODUTO_IA_URL}/descobrir-hardwares`, comparar `identidade`/`chaveComparacao` com o banco e devolver ao frontend apenas os candidatos novos. Antes de cadastrar, deve refazer a deduplicação. O Projeto IA não grava no banco e não retorna preço nesse fluxo.

Variáveis opcionais:

```env
PRODUTO_IA_DISCOVERY_CONCURRENCY=1
DISCOVERY_TOTAL_TIMEOUT_SECONDS=75
DISCOVERY_SOURCE_TIMEOUT_SECONDS=8
DISCOVERY_ENRICHMENT_TIMEOUT_SECONDS=6
DISCOVERY_ENRICHMENT_MAX_SOURCES=2
```

## v14.18 - Open Icecat opcional

Para habilitar a fonte estruturada Icecat, configure `ICECAT_USERNAME`. Tokens de acesso podem ser adicionados em `ICECAT_API_TOKEN` e `ICECAT_CONTENT_TOKEN`. Esses segredos ficam somente no serviço Projeto IA. A ausência dessas variáveis não impede a descoberta por PC-Kombo, CPU-Monkey e TechPowerUp.


## v14.20 — descoberta orientada à qualidade

A descoberta detalha e enriquece por padrão. Ajustes opcionais:

```text
DISCOVERY_TOTAL_TIMEOUT_SECONDS=300
DISCOVERY_ENRICHMENT_TIMEOUT_SECONDS=18
DISCOVERY_ENRICHMENT_MAX_SOURCES=6
```

Esses valores são limites de proteção, não metas de velocidade. A prioridade é preencher a ficha com dados confirmados sem inventar campos.
