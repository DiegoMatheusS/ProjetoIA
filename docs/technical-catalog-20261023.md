# Catálogo técnico e extensão 0.4.0

O cadastro por link, captura da extensão, pesquisa por nome e descoberta passa a separar a identidade do produto do texto de venda. `nome` mantém modelo, variante, código e capacidades; remove chamadas comerciais, histórias e sufixos de loja. A descrição do anúncio permanece em `descricaoAnuncio`; a descrição do catálogo resume especificações conhecidas com unidades. PCs mantêm a configuração completa, acessórios e garantia informados no anúncio.

A pesquisa usa consultas direcionadas aos campos ausentes e tenta a consulta do modelo exato quando a primeira página corresponde a outra variante. Modelos comerciais como HyperX Cloud III são aceitos; palavras genéricas não identificam um modelo. Dados manuais, inclusive `false` e zero, permanecem. Campos contraditórios entre fontes não são preenchidos automaticamente. A fonte, o trecho e o horário acompanham os campos confirmados.

Produtos com ficha em metadados também consultam fabricantes e bases técnicas. Somente atributos explícitos de páginas validadas são aproveitados; preço, frete, textos comerciais e chaves internas são descartados. Sem identificação suficiente ou fonte confirmada, o campo permanece ausente. Este caminho não exige uma chamada paga a um modelo de linguagem.

A extensão captura o preço fracionado do Mercado Livre na página do produto, excluindo preços antigos, parcelas e recomendações. Títulos e JSON-LD de outros produtos ou variantes são rejeitados quando a URL explicita a divergência. A captura local não é enviada como preço manual. A fila persistente e a retomada em caso de indisponibilidade continuam disponíveis.

Atualize o serviço e recarregue a pasta `extension/` no Chrome para usar 0.4.0. Não há alteração obrigatória de chave ou configuração. As fontes e testes Python de `produto_IA/` acompanham os da raiz. Os testes usam páginas, fontes e serviços simulados; não medem a cobertura dos fornecedores em produção.
