# Extensão Criabyte — envio de ofertas

Extensão Manifest V3 para Chrome/Edge. Ela não contém a lógica de cadastro do
Criabyte: apenas envia a página do produto e o link afiliado para a Produto IA.

## Fluxo

1. Abra o anúncio original no navegador.
2. Gere/copiei o link afiliado da loja.
3. Abra a extensão.
4. O campo **Página do produto** usa a aba atual.
5. Cole o **Link afiliado** e clique em **Enviar para Criabyte**.
6. A Produto IA identifica o Hardware e chama o backend do Criabyte:
   - Hardware já existe + anúncio novo: cria somente a nova oferta.
   - Mesmo anúncio já cadastrado: atualiza preço/link afiliado.
   - Hardware não existe: tenta cadastrar o Hardware, cria o Produto de catálogo
     se necessário e cria a oferta inicial.
   - Cadastro técnico inseguro/incompleto: retorna `REVISAO_NECESSARIA`.

Novo Hardware/Produto é criado como **rascunho** (`publicado=false`).

## Configuração

No popup, abra **Configuração** e informe:

- URL pública/local da Produto IA.
- `PRODUTO_IA_API_KEY`, quando configurada no servidor.

A sessão administrativa do Criabyte continua no servidor da Produto IA via
`CRIABYTE_SESSION_TOKEN` ou `CRIABYTE_ADMIN_EMAIL` +
`CRIABYTE_ADMIN_PASSWORD`. A extensão nunca recebe essas credenciais.

## Instalar localmente

Chrome/Edge:

1. Abra a página de extensões.
2. Ative o modo de desenvolvedor.
3. Escolha **Carregar sem compactação**.
4. Selecione esta pasta `extension/`.

O endpoint usado é:

`POST /extensao/importar-oferta`

Payload:

```json
{
  "urlProduto": "https://loja.com/anuncio",
  "urlAfiliada": "https://link-afiliado.example/..."
}
```
