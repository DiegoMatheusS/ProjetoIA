# Produto IA — CriaByte (Python)

## Atualização v14.8

A v14.8 adiciona fallback 100% em nuvem com Browserless. Quando HTTP, Chromium da Railway e URLs oficiais equivalentes do Magalu/Magazine Luiza falham, a IA conecta a um navegador Browserless usando as variáveis `BROWSERLESS_TOKEN`, `BROWSERLESS_PROXY` e `BROWSERLESS_PROXY_COUNTRY`. O padrão recomendado é proxy residencial no Brasil, com IP sticky, locale compatível e modo stealth. O token não é retornado na API nem gravado nos logs.


## Atualização v14.6

A v14.6 adiciona fallback de coleta para ambientes de nuvem: detecta páginas de verificação do Magalu/Magazine Você, tenta Chromium/Playwright e, quando aplicável, a página pública equivalente do Magazine Luiza. Se todos os caminhos estiverem bloqueados, retorna erro estruturado sem inventar dados de produto. O cache de Magalu foi versionado para descartar capturas inválidas antigas.

A v14.2 reforça a normalização do Magalu com casos reais de PC montado, CPU, GPU e placa-mãe: PC Gamer completo tem prioridade sobre componentes internos, marca confirmada no título vence atributo genérico conflitante, GPU separa modelo comercial de MPN e nomes comerciais com espaços não são promovidos a MPN automaticamente.


Coletor de URLs de produtos alinhado ao frontend e ao backend do CriaByte.

Princípios:
- Hardware técnico separado de Oferta/preço.
- Não inventar especificações. Campo sem fonte confirmada fica ausente. A v14 pode complementar lacunas com fonte externa validada, mantendo a origem do dado.
- Imagem é armazenada apenas como URL; o coletor não baixa a imagem.
- Mercado Livre usa API oficial como fonte principal.
- Outras lojas usam JSON-LD/ficha técnica e, se necessário, um único fallback de navegador.
- Cadastro/análise continua com uma URL individual por execução. O recálculo de preços possui um modo em lote separado, sequencial e restrito a Oferta/preço/disponibilidade.

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
PYTHONPATH=. pytest -q
```

## Magalu bloqueado no Codespaces — captura pelo navegador local

Se o Magalu retornar `403` no Codespaces, não tente contornar o bloqueio. Faça a
captura pelo Chrome do seu próprio computador:

```bash
python -m src.local_browser_capture "URL_DO_MAGALU" --output magalu_capture.json
```

Quando a página carregar, pressione ENTER no terminal. Depois envie o arquivo
`magalu_capture.json` para o Codespaces e processe:

```bash
python -m src.main "URL_DO_MAGALU" --local-capture magalu_capture.json
```

O arquivo guarda HTML/texto/URL/título da página, sem cookies ou senhas. Veja
`CAPTURA_LOCAL_MAGALU.txt` para o passo a passo no Windows.

## v8 — Magalu: GPU, placa-mãe e RAM

A v8 foi validada com capturas reais do Magazine Você/Magalu para placa de vídeo, placa-mãe e memória RAM. O coletor prioriza códigos de fabricante explícitos, extrai mais campos técnicos por categoria e mantém a regra conservadora: campos ausentes não são inventados. Dados de vendedor, entrega, frete e pagamento não entram no resultado de produto.

## v9 — Magalu: armazenamento, fonte, gabinete, coolers, notebook e monitor

A v9 é cumulativa e inclui as correções das v7/v8. Foi validada com capturas reais do Magazine Você/Magalu para SSD, fonte, gabinete, air cooler, water cooler, notebook e monitor. O parser passou a interpretar mais campos do contrato do backend sem completar lacunas por conhecimento externo. Em particular, não transforma versão HDMI 2.1 em contagem de portas, não usa dimensões ambíguas como medidas técnicas e mantém ausentes os campos que a página não informa.

Para uma captura local:

```bash
python -m src.main "URL_DO_PRODUTO" --local-capture arquivo.json
```

O resultado continua focado no produto: vendedor, entrega, frete e pagamento ficam fora do payload coletado.


## v10 — Magalu: 10 testes reais adicionais

A v10 é cumulativa e inclui as versões v7, v8 e v9. Foi validada com dez novas capturas reais: fonte modular, teclado, RAM DDR5 2x16 GB, ventoinha, GPU moderna, headset, mouse, notebook gamer, microfone e placa-mãe Intel.

Além de ampliar os extratores por categoria, a v10 corrige ambiguidades observadas nas páginas reais, como `HDMI 2.1` sendo confundido com quantidade de portas e a serialização do Magalu `DisplayPort 2.1: 3 x HDMI | 2.1: 1x`. A ficha técnica explícita continua tendo prioridade sobre texto promocional conflitante, e campos sem evidência permanecem ausentes.

Validação: 45 testes automatizados aprovados e 10 capturas reais processadas ponta a ponta.

## v11 — Magalu: variações e casos-limite reais

A v11 é cumulativa e substitui as versões anteriores. Foi validada com 13 capturas reais adicionais: fonte não modular, fonte semi-modular, gabinete Mid Tower ATX, monitor OLED, monitor ultrawide, HD SATA 3.5", SSD SATA 2.5", SSD NVMe PCIe 5.0, Intel LGA1700, Intel LGA1851, Ryzen sem vídeo integrado, mouse Bluetooth/USB sem fio e teclado Bluetooth sem fio.

Correções principais da v11:
- `FCLGA1700` é normalizado para `LGA1700` sem alterar sockets AMD.
- HD SATA 3.5" não é confundido com SAS e capacidade em TB é convertida corretamente para GB.
- SSD PCIe 5.0 extrai geração, pistas e velocidades com números contendo separador de milhar.
- `80 Plus Gold` não é tratado como eficiência de 80%; eficiência só entra quando há porcentagem explícita.
- Fontes semi-modulares reconhecem conectores descritos no formato detalhado do Magalu.
- Gabinetes com dimensões `L x W x H` rotuladas são convertidos corretamente para profundidade/largura/altura e preservam compatibilidade ATX/M-ATX/ITX.
- Mouse Bluetooth com receptor USB não é marcado como mouse cabeado.
- Teclado Bluetooth é reconhecido como wireless; `Compacto` é tratado como tamanho, não como tecnologia de switch.
- `S Vídeo` / `S Cooler` em títulos de processadores é interpretado como ausência explícita, sem adivinhar.
- Marca rotulada da ficha prevalece sobre metadados genéricos; MPN continua separado do modelo comercial quando a própria página fornece evidência.

A captura Intel LGA1851 usada no teste não informa explicitamente os tipos de memória suportados. Esse campo permanece ausente por design, em vez de ser preenchido por conhecimento externo.

Validação: 59 testes automatizados aprovados e 13 capturas reais adicionais processadas ponta a ponta.

## v12 — Magalu: robustez de produção

A v12 é cumulativa e substitui a v11. O foco desta versão não é ampliar o número de categorias, e sim tornar a coleta individual do Magazine Você/Magalu mais segura para uso real antes da integração com o banco do CriaByte.

Ajustes principais:
- rejeita URL de busca/listagem que não seja página individual de produto;
- retorna erro controlado para HTTP 404/410;
- detecta captura local incompleta antes de tentar normalizar dados;
- melhora a separação entre preço Pix, preço normal, preço anterior e parcelamento;
- mantém `precoAnterior` vazio quando não existe promoção explícita;
- detecta indisponibilidade sem inventar preço;
- valida GTIN/EAN pelo dígito verificador GS1 e também procura o código na ficha técnica;
- não transforma SKU/código Magalu em MPN;
- captura variantes explicitamente selecionadas no HTML quando disponíveis;
- sinaliza kits/combos e componentes/quantidade detectáveis sem inventar composição;
- mantém a categoria baseada no produto real, não na categoria comercial da loja;
- quando o título é ambíguo, usa ficha técnica/atributos como fallback de classificação;
- produto fora das categorias do CriaByte recebe erro controlado e não vira Hardware;
- gera chaves de comparação por GTIN, `marca + MPN` e `marca + modelo` para preparar futura deduplicação no banco.

O fluxo continua sendo de **uma URL por execução**. Não foi adicionado processamento em lote.

Validação desta versão: **74 testes automatizados aprovados** (59 anteriores + 15 novos testes de robustez da v12).


## v13 — enriquecimento técnico + recálculo de preços em lote

A v13 é cumulativa e substitui a v12. O fluxo principal de cadastro continua sendo **um produto por vez**. Foram adicionados dois recursos separados:

### 1. Enriquecimento técnico opcional

Quando a loja não traz uma especificação e a identidade do produto está confirmada por `GTIN`, `marca + MPN` ou `marca + modelo` forte, a ferramenta pode consultar outras fontes. A ordem é:

1. site oficial do fabricante;
2. TechPowerUp (GPU);
3. PC-Kombo;
4. Geizhals.

Uso:

```bash
python -m src.main "URL_DO_PRODUTO" --enrich
```

O enriquecimento **só preenche campos ausentes**. Se outra fonte discordar de um valor já coletado, a v13 mantém o valor principal e registra o conflito em `enriquecimentoTecnico.conflitos` para revisão. Cada campo complementado registra sua fonte/URL em `origemPorCampo`.

A descoberta externa é conservadora: uma página candidata precisa conter o identificador forte do produto. A ferramenta não tenta contornar 403, CAPTCHA ou outros bloqueios.

Para ativar enriquecimento automaticamente no fluxo individual:

```text
ENRICHMENT_AUTO=true
```

### 2. Recalcular preços em lote

Este modo existe para o botão de manutenção de preços do CriaByte. Ele recebe vários links, mas processa **uma URL por vez**, sem paralelismo e sem alterar ficha técnica. O resultado contém apenas as mudanças de preço/disponibilidade que precisam ser aplicadas às Ofertas.

Aceita JSON, CSV ou TXT:

```bash
python -m src.main --batch-prices ofertas.json
python -m src.main --batch-prices ofertas.csv --batch-output resultado.json
python -m src.main --batch-prices links.txt --batch-output resultado.json
```

Formato recomendado vindo do CriaByte:

```json
{
  "ofertas": [
    {
      "produtoId": "...",
      "ofertaId": "...",
      "nome": "AMD Ryzen 7 7800X3D",
      "url": "https://...",
      "precoAtual": 2199.90,
      "disponivelAtual": true
    }
  ]
}
```

Saída resumida:

```json
{
  "resumo": {
    "total": 10,
    "atualizar": 3,
    "semAlteracao": 6,
    "erros": 1
  },
  "atualizacoes": []
}
```

O módulo de lote prepara as alterações para o CriaByte, mas **não grava diretamente no banco por conta própria**. A aplicação das alterações deve continuar sendo feita pelo backend do CriaByte/botão `Recalcular preços`, usando a lista `atualizacoes`. Assim a Produto IA não precisa conhecer nem guardar credenciais administrativas do banco.

Validação desta versão: **91 testes automatizados aprovados** (74 anteriores + 17 novos testes da v13).

## v14 — integração com o banco real do CriaByte

A v14 é cumulativa e substitui a v13. Ela foi alinhada aos contratos reais do backend enviado em 26/08/2026.

O cadastro principal continua sendo **1 produto/URL por vez**. A diferença é que agora a análise pode consultar o CriaByte antes de sugerir criação ou alteração.

### Fluxo individual v14

```text
URL
 ↓
Magalu / Mercado Livre
 ↓
normalização
 ↓
enriquecimento técnico opcional
 ↓
consulta ao CriaByte
 ↓
Hardware existe?
Produto existe?
Oferta existe?
 ↓
plano de ações seguro
```

Uso:

```bash
python -m src.main "URL_DO_PRODUTO" --enrich --criabyte-plan
```

Salvar o resultado:

```bash
python -m src.main "URL_DO_PRODUTO" --enrich --criabyte-plan --criabyte-output analise_criabyte.json
```

A v14 **não aplica alterações automaticamente**. Ela consulta as rotas administrativas e gera `integracaoCriaByte.acoesSugeridas` no formato esperado pelo backend. Isso permite integrar o mesmo planejamento ao backend e ao frontend depois, sem risco de a ferramenta alterar produção durante o desenvolvimento.

### Identificação de registro existente

Prioridade conservadora:

1. GTIN/EAN exato + marca compatível;
2. MPN exato + marca compatível;
3. marca + modelo exatos;
4. nome muito semelhante + mesma marca é apenas candidato para revisão, nunca match automático.

**Marca diferente não é tratada como o mesmo Produto apenas porque o nome/modelo se parece.**

Se GTIN ou MPN coincidirem mas a marca for diferente, a v14 registra conflito de identidade e bloqueia criação/alteração automática.

### Preenchimento de campos vazios

Quando Hardware ou Produto já existe:

- `null`, string vazia e lista vazia podem ser preenchidos;
- valor já preenchido é preservado;
- valor diferente vira conflito para revisão;
- `false` e `0` são valores válidos e não são tratados como vazios;
- IDs internos e campos do Prisma nunca entram no PATCH.

Para especificações técnicas do Hardware, a v14 monta um **objeto mesclado completo** antes de sugerir o PATCH. Isso é necessário porque os DTOs do backend possuem campos obrigatórios em várias categorias. A ferramenta não envia um fragmento inválido que apagaria ou deixaria de validar a especificação atual.

### Separação Hardware / Produto / Oferta

A v14 mantém a regra rígida:

```text
Hardware = dados técnicos
Produto  = identidade comercial
Oferta   = preço + disponibilidade + URL/parceiro
```

`preco` e `precoAnterior` nunca são enviados em payload de Hardware ou Produto.

Para novo Hardware técnico, a ordem sugerida é:

```text
POST /hardwares
POST /admin/produtos/de-hardware/{hardwareIdCriado}
POST /admin/ofertas
```

Para produto genérico/periférico:

```text
POST /admin/produtos
POST /admin/ofertas
```

A categoria comercial é resolvida pelo `slug` real retornado por `/admin/categorias-produto`, em vez de inventar `categoriaId`.

### Oferta existente

A v14 compara Produto + Parceiro + URL original normalizada. Se a Oferta existe:

```text
PATCH /admin/ofertas/:id
```

O payload usa o contrato real `AtualizarOfertaDto`:

```json
{
  "preco": 1999.90,
  "status": "ATIVA"
}
```

Quando apenas o preço muda, a Produto IA envia somente `preco`. O backend atual já transforma o preço salvo anterior em `precoAnterior` e cria o histórico.

Quando a página confirma indisponibilidade, a atualização usa:

```json
{
  "status": "INDISPONIVEL"
}
```

### Recalcular preços em lote — alinhado ao backend

O modo `--batch-prices` continua processando vários links **sequencialmente e um por vez**, mas agora cada alteração inclui também:

```json
{
  "rotaBackend": "/admin/ofertas/123",
  "metodoBackend": "PATCH",
  "payloadBackend": {
    "preco": 899.90,
    "status": "ATIVA"
  }
}
```

A v14 aceita Oferta que tenha somente `urlOriginal`. `urlAfiliada` é fallback e não é requisito do módulo Python.

**Atenção para a futura integração do backend:** no backend analisado, o método `verificarPrecosOfertas` ainda filtra o lote por `urlAfiliada != null`. Quando a Produto IA for incorporada ao backend, esse filtro deve ser ajustado para permitir Oferta com `urlOriginal`, mantendo `urlAfiliada` apenas como fallback de consulta.

### Limitações tratadas explicitamente

- Nova Oferta indisponível não é criada silenciosamente como `ATIVA`, porque a rota de criação atual fixa o status inicial como `ATIVA`; o plano sinaliza esse caso.
- Hardware e Produto existentes, mas sem vínculo entre si, são sinalizados para revisão em vez de criar duplicidade.
- Notebook e PC Montado continuam exigindo as rotas especializadas do backend.
- `FONE` não envia `especificacaoHeadset`: o backend atual aceita essa tabela específica somente para a categoria `headsets`.

### Validação v14

**104 testes automatizados aprovados.**

A v14 continua incluindo todos os recursos da v11, v12 e v13. Para atualizar o projeto, use diretamente a versão mais nova; não é necessário aplicar as versões anteriores em sequência.

## v14.6 - fallback de captura local

Quando a coleta cloud do Magalu retornar `MAGALU_COLETA_BLOQUEADA`, o serviço
pode receber uma captura feita no Chrome do ADMIN via `POST /analisar-captura`.
A captura local resolve apenas o acesso à página; toda a normalização continua
centralizada na Produto IA da Railway.
