# Descoberta de ofertas em Mercado Livre e Magalu

A rota interna autenticada POST /ofertas/descobrir consulta Mercado Livre e Magazine Luiza por termo, limite e filtro de promoções. Reaproveita o cliente oficial do Mercado Livre quando disponível e os coletores de listagem e produto já existentes. Magalu usa suas páginas públicas; não presume uma API pública de afiliados.

A seleção exige título correspondente ao item vendido, modelo e variante pesquisados. Suporte, adaptador, cabo, cooler, recarga e outras peças citando o modelo não viram a peça principal. Essa proteção também se aplica à procura automática de ofertas idênticas. Preço e disponibilidade precisam vir da loja, não de snippets de buscador. Não é inventado link afiliado.

A coleta pública limita detalhes e tempo; devolve avisos de resultado parcial e bloqueio, mais o link para abrir a busca na loja. Não contorna CAPTCHA ou acesso negado. Fontes Python de compatibilidade sincronizadas. Testes usam respostas simuladas; a cobertura real depende do acesso liberado pelas lojas.
