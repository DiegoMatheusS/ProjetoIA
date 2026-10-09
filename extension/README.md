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
- Mesmo produto com outro anúncio/vendedor do Mercado Livre: mantém a ficha e adiciona outra oferta com seu próprio link e preço, inclusive em páginas de catálogo com `wid`, `item_id` ou `pdp_filters`.
- Hardware não existe: cadastra Hardware/Produto e cria a oferta inicial.
- PC montado não existe: cadastra um Produto do tipo BUILD com a descrição/configuração do anúncio e a oferta inicial. A extensão não cria vínculos de peças sem identificação confirmada no catálogo.
- PC montado já cadastrado: reaproveita o Produto e cria ou atualiza a oferta.
- Mousepads são identificados antes de mouse; fones de ouvido, headphones, earbuds/TWS, AirPods e Galaxy Buds usam a categoria Fones. Anúncios explicitamente identificados como headset continuam em Headsets.
- Cadastro técnico inseguro/incompleto: retorna revisão necessária.
- Se o preço não puder ser coletado, a extensão abre um campo **Preço do anúncio (R$)** para preenchimento manual e permite concluir sem sair da janela.
- Se faltar a descrição do PC, um campo de texto permite informar a configuração e a garantia.
- Para armazenamento M.2, a extensão solicita comprimento e chave quando não forem encontrados. Informe o comprimento em milímetros: **2280 = 80 mm**, **2230 = 30 mm**, **2242 = 42 mm**, **2260 = 60 mm**, **22110 = 110 mm**. A chave pode ser M, B ou B_M (B+M).

Os cadastros concluídos pela integração ficam publicados (`publicado=true`).

### Atualização 0.2.7

O cadastro automático de PC montado requer as alterações correspondentes implantadas em **ProjetoIA** e **backend_pc3D**. Atualizar somente os arquivos da extensão não instala as mudanças nos servidores.

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

O endpoint usado pelo hook de captura local é:

`POST /extensao/importar-oferta-v2`

O endpoint anterior `POST /extensao/importar-oferta` continua suportado, inclusive para PC montado e revisão dos campos M.2.

## Ícone

A extensão usa o ícone oficial do Criabyte com apenas o **C** branco no fundo azul, em PNG 16/32/48/128 px para o Chrome.
