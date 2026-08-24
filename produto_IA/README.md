# Produto IA - CriaByte

Coletor inicial de produtos alinhado à `main` do backend CriaByte.

## Objetivo atual

Receber uma URL de produto, coletar dados públicos da página e devolver um payload parcial compatível com o backend.

O projeto separa:

- dados técnicos de Hardware;
- especificações de periféricos como Produto;
- Notebook como cadastro especializado;
- preço e disponibilidade como Oferta;
- imagem somente como URL.

## Fontes

Prioridade atual:

1. lojas/varejistas;
2. fabricantes;
3. fonte genérica quando o domínio não é reconhecido.

Mercado Livre está bloqueado nesta versão para evitar depender dele como fonte principal.

## Instalação

```bash
npm install
npx playwright install --with-deps chromium
```

## Uso

```bash
npm start -- "https://site.com/produto"
```

Categoria forçada, se necessário:

```bash
npm start -- "https://site.com/produto" TECLADO
```

## Saída

O programa retorna:

- categoria detectada;
- fonte e vendedor detectados;
- payload parcial compatível com o backend;
- especificações encontradas;
- campos obrigatórios ausentes;
- preço atual e anterior quando encontrados;
- disponibilidade;
- URL original;
- imagem somente como URL;
- avisos básicos de validação.

## Regra de precisão

O coletor não deve preencher um campo técnico apenas porque uma palavra apareceu na página. Ele prioriza valores rotulados e trechos da ficha técnica. Quando não há evidência suficiente, o campo fica ausente.

A IA local ainda não é usada. Ela será adicionada depois como interpretador de casos difíceis, sempre limitada ao schema real do backend.
