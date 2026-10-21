# Agente e extensão 0.3.0

A extensão cria uma operação e consulta seu estado. Fechar a janela não interrompe o trabalho do servidor; **Retomar envio** recupera o resultado. Uma chave de idempotência impede cadastrar duas vezes ao repetir a mesma solicitação. O histórico é separado por dispositivo.

Há cancelamento antes da gravação. Quando a gravação já começou, a operação precisa terminar antes de decidir sobre um reenvio. Uma reinicialização durante uma gravação deixa o resultado como interrompido e exige conferir o catálogo; não há repetição automática de uma mutação de resultado desconhecido.

## Armazenamento e configuração

- Montar um volume persistente e definir `PRODUTO_IA_STATE_DB`, por exemplo `/data/criabyte/operations.sqlite3`. O caminho padrão `.data/operations.sqlite3` funciona localmente, mas precisa de volume para sobreviver a novas implantações. Usar uma réplica por arquivo SQLite; réplicas em hosts diferentes exigem uma fila/banco compartilhado.
- `PRODUTO_IA_IMPORT_CONCURRENCY` controla os trabalhadores da extensão (1 por padrão, máximo 4). O limite de análise é compartilhado com os demais pedidos de coleta.
- `PRODUTO_IA_API_KEY` continua sendo a chave interna entre servidores. Ausência da chave passa a recusar chamadas protegidas.
- Chaves próprias são criadas e revogadas no painel administrativo do CriaByte. Só os hashes ficam armazenados; têm validade de um ano. A primeira chave própria encerra o uso da chave de serviço pela extensão. Até essa migração, a instalação anterior continua compatível. `PRODUTO_IA_ALLOW_LEGACY_EXTENSION_KEY=false` desabilita explicitamente essa transição.
- Como alternativa operacional, `PRODUTO_IA_EXTENSION_KEYS` aceita JSON de nomes de dispositivos para valores `sha256:HASH_DO_TOKEN`. Não colocar o token do serviço nesse mapa.
- `PRODUTO_IA_MAX_DAILY_AI_CALLS` limita chamadas externas por dia UTC; 0 deixa a quota desabilitada. Respostas reutilizadas do cache não consomem outra chamada.
- `AI_COST_USD_PER_MILLION` aceita JSON por `PROVEDOR/modelo`, com `input` e `output` em dólares por milhão de tokens. Sem tabela ou sem uso informado, o custo permanece desconhecido. A estimativa não inclui tarifas adicionais de ferramentas/busca.

O resumo autenticado `/admin/operacoes/resumo` reúne operações, duração, uso de tokens e qualidade dos campos. Não armazena prompts ou credenciais nas métricas.

## Atualização

Implantar este serviço, depois backend_pc3D e frontend_pc3D. Recarregar a pasta `extension/` no Chrome para instalar 0.3.0. No painel, criar uma chave com o nome do computador e colá-la em **Configuração** da extensão. A URL do serviço continua igual.

As correções de preenchimento automático de Produtos e descoberta ampliada estão incluídas. As fontes de compatibilidade em `produto_IA/` foram atualizadas com os módulos da raiz. O Dockerfile principal usa `src.app:app`.

## Testes

`python -m pytest -q tests` cobre pesquisa, catálogo, extração, isolamento de dados comerciais, autenticação, fila, retomada, cancelamento, chaves revogadas e quota. As integrações externas são simuladas. O workflow também verifica a sintaxe JavaScript da extensão.
