# Extensão Criabyte — envio de ofertas

Extensão Manifest V3 focada no Google Chrome. A extensão envia a página do
produto e o link afiliado para a Produto IA; toda a identificação e integração
com o catálogo do Criabyte continuam no servidor.

## Como funciona

1. Abra o anúncio original no Chrome.
2. Clique no ícone **Criabyte - Enviar oferta**.
3. A extensão abre uma janela própria, que continua aberta quando você clica
   fora e só é encerrada ao fechar a janela.
4. Para mantê-la realmente sobre outras janelas, clique em **Fixar sobre tudo**.
5. **Página do produto** recebe automaticamente a aba que estava ativa.
6. Cole o **Link afiliado**.
7. Clique em **Enviar para Criabyte**.

Resultados possíveis:

- Hardware já existe + anúncio novo: cria somente a nova oferta.
- Mesmo anúncio já cadastrado: atualiza preço e link afiliado.
- Hardware não existe: cadastra Hardware/Produto e cria a oferta inicial.
- Cadastro técnico inseguro/incompleto: retorna revisão necessária.

Novos Hardwares/Produtos ficam como rascunho (`publicado=false`).

## Configuração

A URL de produção já vem preenchida:

`https://projetoia-production.up.railway.app`

Só é necessário informar `PRODUTO_IA_API_KEY` uma vez. A configuração fica
salva no armazenamento local do Chrome.

A extensão não recebe login ou senha administrativa do Criabyte. A comunicação
Produto IA → backend usa uma rota interna autenticada pela mesma
`PRODUTO_IA_API_KEY` configurada nos dois serviços.

## Instalar/atualizar localmente no Chrome

1. Atualize o repositório.
2. Abra `chrome://extensions`.
3. Ative **Modo do desenvolvedor**.
4. Em uma instalação nova, clique em **Carregar sem compactação** e selecione
   a pasta `extension/`.
5. Se a extensão já estiver instalada, clique no botão **Atualizar** ou no
   ícone de recarregar do card da extensão depois de atualizar os arquivos.

O endpoint público da extensão é:

`POST /extensao/importar-oferta`

## Ícone

A extensão usa o ícone oficial do Criabyte com apenas o **C** branco no fundo azul, em PNG 16/32/48/128 px para o Chrome.
