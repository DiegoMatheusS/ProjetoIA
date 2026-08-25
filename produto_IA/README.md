# Produto IA - Python

Coletor de produtos alinhado ao backend CriaByte, com Mercado Livre via API oficial e navegador como fallback.

## Instalação no Codespaces

```bash
cd /workspaces/ProjetoIA/produto_IA
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
```

## Teste sem API

```bash
python -m src.main "URL_DO_PRODUTO"
```

Mercado Livre pode redirecionar o navegador para verificação. Para evitar isso, configure a API oficial.

## Mercado Livre - criar e autorizar a aplicação

### 1. Descobrir Redirect URI do Codespaces

```bash
python -m src.auth.mercadolivre_oauth codespace-uri
```

Copie a URL exibida e use exatamente essa URL como Redirect URI no DevCenter do Mercado Livre.

### 2. Configure o `.env`

Mantenha suas variáveis atuais e adicione:

```text
ML_CLIENT_ID=SEU_CLIENT_ID
ML_CLIENT_SECRET=SEU_CLIENT_SECRET
ML_REDIRECT_URI=URL_HTTPS_EXATA_CADASTRADA_NO_MERCADO_LIVRE
ML_USE_PKCE=false
```

Nunca envie o Client Secret, Access Token ou Refresh Token para o GitHub.

### 3. Inicie o callback no Codespaces

```bash
python -m src.auth.ml_callback_server
```

A porta usada é `8765`. No painel **Ports** do Codespaces, deixe a porta acessível no navegador enquanto fizer a autorização.

### 4. Em outro terminal, gere a URL de autorização

```bash
python -m src.auth.mercadolivre_oauth auth-url
```

Abra a URL exibida no navegador, faça login com a conta principal do Mercado Livre e autorize. O callback troca o `code` pelo token e grava `ML_ACCESS_TOKEN` e `ML_REFRESH_TOKEN` no `.env`.

### 5. Confirme

```bash
python -m src.auth.mercadolivre_oauth status
python -m src.auth.mercadolivre_oauth whoami
```

O comando `whoami` não mostra token nem secret.

### 6. Teste o produto

```bash
python -m src.main "URL_DO_MERCADO_LIVRE" --no-browser
```

Procure no JSON:

```json
"apiUsada": true
```

## Renovação de token

O projeto tenta renovar automaticamente um access token expirado quando `ML_REFRESH_TOKEN`, `ML_CLIENT_ID` e `ML_CLIENT_SECRET` estão configurados. O novo refresh token é salvo no `.env`, porque o Mercado Livre invalida o anterior após uso.

Também é possível renovar manualmente:

```bash
python -m src.auth.mercadolivre_oauth refresh
```

## Segurança

- `.env` está no `.gitignore`.
- O ZIP de atualização não contém seu `.env`.
- Não envie Client Secret, Access Token ou Refresh Token em chat, commit ou screenshot.
