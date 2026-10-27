# Ficha técnica sem dados comerciais

A coleta técnica continua preservando material, cor, capacidade, rendimento, compatibilidade, códigos do produto e valores como false e zero. O filtro retira avaliações, rankings de vendas, preço, entrega, frete, parcelas, pagamento e scripts da ficha técnica. O preço da oferta continua no seu campo comercial.

A extensão 0.4.2 filtra os pares capturados na aba; o agente repete a validação na entrada e na saída dos cadastros. O site filtra também a apresentação de fichas antigas, sem alterar em massa os dados do banco. Cadastros legados não precisam ser reimportados para ocultar essas linhas após atualizar o frontend.

Os testes incluem o formato de avaliações da Amazon com JavaScript, atributos por ID de marketplace, sistema operacional, material, compatibilidade e rank de memória.
