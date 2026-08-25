# Produto IA — CriaByte (Python)

Coletor de URLs de produtos alinhado ao frontend e ao backend do CriaByte.

Princípios:
- Hardware técnico separado de Oferta/preço.
- Não inventar especificações. Campo não confirmado fica ausente.
- Imagem é armazenada apenas como URL; o coletor não baixa a imagem.
- Mercado Livre usa API oficial como fonte principal.
- Outras lojas usam JSON-LD/ficha técnica e, se necessário, um único fallback de navegador.
- Não é crawler em massa: trabalha com uma URL individual por execução.

## Categorias cobertas

### Componentes técnicos
`PROCESSADOR`, `PLACA_MAE`, `MEMORIA_RAM`, `PLACA_VIDEO`, `ARMAZENAMENTO`, `FONTE`, `GABINETE`, `COOLER`, `VENTOINHA`.

### Loja / periféricos / setup
`MONITOR`, `MOUSE`, `TECLADO`, `HEADSET`, `FONE`, `MICROFONE`, `WEBCAM`, `CONTROLE`, `MOUSEPAD`, `CADEIRA`, `MESA`, `SUPORTE_MONITOR`, `ILUMINACAO`, `ORGANIZADOR_CABOS`, `ACESSORIO`.

### Especiais
`NOTEBOOK`, `CELULAR`, `PC_MONTADO`.

O arquivo `config/criabyte_categories.json` lista o contrato de campos por categoria.

## Instalação no Codespaces

```bash
cd /workspaces/ProjetoIA/produto_IA
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

## Uso

```bash
python -m src.main "URL_DO_PRODUTO"
```

Sem fallback de navegador:

```bash
python -m src.main "URL_DO_PRODUTO" --no-browser
```

Forçando uma categoria quando você já sabe o destino:

```bash
python -m src.main "URL_DO_PRODUTO" PLACA_MAE --no-browser
python -m src.main "URL_DO_PRODUTO" NOTEBOOK --no-browser
```

## Ritmo de coleta

Os padrões já são conservadores:

```text
REQUEST_MIN_DELAY_SECONDS=1.25
REQUEST_JITTER_SECONDS=0.45
ML_MIN_DELAY_SECONDS=1.0
ML_JITTER_SECONDS=0.35
BROWSER_MIN_DELAY_SECONDS=1.8
BROWSER_JITTER_SECONDS=0.6
HTTP_MAX_RETRIES=2
```

O Mercado Livre também usa cache curto. Produtos técnicos podem ficar em cache por mais tempo; preço/ofertas têm cache curto.

Se `/items/{id}` estiver proibido para a aplicação, o coletor não insiste por padrão em `/sale_price` e `/prices`; ele segue para o catálogo e `/products/{id}/items`. Para testar esses endpoints manualmente:

```text
ML_TRY_RESTRICTED_PRICE_ENDPOINTS=true
```

## Mercado Livre OAuth

Descobrir callback do Codespaces:

```bash
python -m src.auth.mercadolivre_oauth codespace-uri
```

No `.env`:

```text
ML_CLIENT_ID=...
ML_CLIENT_SECRET=...
ML_REDIRECT_URI=https://...-8765.app.github.dev/callback
ML_USE_PKCE=false
```

Iniciar callback:

```bash
python -m src.auth.ml_callback_server
```

Em outro terminal:

```bash
python -m src.auth.mercadolivre_oauth auth-url
```

Confirmar autenticação:

```bash
python -m src.auth.mercadolivre_oauth whoami
```

Nunca versione `.env`, Client Secret, Access Token ou Refresh Token.

## Testes

```bash
pip install -r requirements-dev.txt
pytest -q
```
