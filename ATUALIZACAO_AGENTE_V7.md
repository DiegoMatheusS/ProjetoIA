# Agente de pesquisa técnica V7

A V7 adiciona resolução conservadora de conflitos entre fontes que já foram coletadas durante o `Completar com IA`.

## Regra principal

Valores que já existiam no payload recebido do frontend continuam imutáveis. O resolvedor atua somente sobre campos preenchidos automaticamente pelo agente.

Quando fontes diferentes retornam valores incompatíveis para o mesmo campo, o agente passa a considerar:

- quantidade de fontes independentes que apoiam cada valor;
- confiança configurada de cada fonte;
- diferença mínima de confiança para aceitar uma fonte claramente superior;
- consenso mínimo de fontes para aceitar um valor por maioria técnica.

Sem vencedor claro, o conflito continua pendente e segue para a auditoria/revisão.

## Variáveis

```env
TECH_RESEARCH_RESOLVE_LIVE_CONFLICTS=true
TECH_RESEARCH_CONSENSUS_MIN_SOURCES=2
TECH_RESEARCH_CONSENSUS_MIN_DELTA=0.08
```

Essa etapa trabalha apenas sobre resultados que já estão em memória e não cria novas requisições externas, portanto não aumenta o orçamento de rede do agente.

## Segurança

O backup anterior à transformação do agente continua disponível em `backup/pre-agente-pesquisa-20260915`.
