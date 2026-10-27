# Verificação das regras nas bases

Para estudar a implementação com diagramas e exemplos completos, leia o [guia de validação](../docs/validacao.md), os [fluxogramas](../docs/fluxos.md) e o [mapa do backend](../docs/backend.md).

Cada análise reúne documentos normativos e bases CSV. O processamento agora interpreta
com IA o significado das colunas e verifica todas as regras extraídas, inclusive as que
não receberam uma associação com bases durante a extração.

## Fluxo

1. No envio do CSV, o parser detecta os tipos físicos. O Gemini acrescenta significado,
   evento (ex.: assinatura ou entrega), unidade, confiança e justificativa por coluna.
   Os metadados ficam no JSON `datasets.columns`; as linhas continuam no storage.
2. A IA recebe as regras e os metadados das bases e propõe escopo e critérios de
   cumprimento. Os planos só usam as operações permitidas em `schemas/validation.py`.
3. O motor Python confere as linhas aplicáveis, sem executar código ou SQL gerados.
   As operações incluem valores, preenchimento, categorias, comparação entre colunas,
   diferenças de datas, datas limite em dias/meses/anos e percentuais.
4. O resultado de cada regra fica em `rules.validation`, separado do status da revisão
   humana. O plano é guardado internamente para reproduzir as evidências paginadas.

Resultados: `conforme`, `violacao`, `inconclusiva`, `nao_aplicavel`, `erro`,
`desatualizada` e `ignorada` (regra rejeitada pela pessoa). Nenhum registro aplicável
significa "não se aplica", nunca conformidade. Dados ausentes, colunas ambíguas,
operações não suportadas e ausência de evidências são explicitados no resultado.

## API e interface

- `POST /api/v1/documents/{id}/validation?refresh_columns=true`: reinterpreta as colunas
  e verifica todas as regras; devolve 202, com o documento em `extracting_rules`.
- `GET /api/v1/documents/{id}/rules`: inclui resultado, contagens, explicação, dados
  faltantes e bases verificadas de cada regra.
- `GET /api/v1/rules/{id}/validation/records?dataset_id=...&verdict=violacao&offset=0&limit=100`:
  evidências de cada registro, com paginação e filtro opcional por resultado.
- O Assistente apresenta o resumo geral, a coluna "Validação nas bases" e o botão
  "Validar todas as regras". Selecionar uma regra abre seus registros e evidências.
- O painel "Ver busca" preserva as consultas existentes, inclusive as corrigidas à mão.

## Atualização e limites

A extração de um documento verifica as regras automaticamente. Uma base nova que termina
de ser lida também inicia nova verificação dos documentos prontos da análise. Mudanças
nas bases ou na interpretação das colunas invalidam resultados anteriores. Alterações
no tipo/resumo de uma regra também exigem nova verificação. Reinícios deixam avaliações
interrompidas pendentes para nova execução.

Prazos em dias úteis dependem de evidência adequada de dias úteis ou de calendário e
localidade; nunca são calculados como dias corridos. Cruzamentos entre bases e critérios
qualitativos sem evidência observável são informados como inconclusivos. A interpretação
normativa continua sujeita à revisão humana. A IA recebe metadados e exemplos, não o CSV
inteiro; o motor percorre todas as linhas do arquivo guardado.

O limite de armazenamento já existente pode cortar CSVs. O tamanho original passa a ser
registrado e a interface informa bases parciais; elas impedem uma conclusão geral de
conformidade. Reenvie o arquivo completo após ajustar o armazenamento.

## Configuração e verificação

Usa `GEMINI_API_KEY`, `GEMINI_MODEL` e os limites de concorrência já existentes. A falha
na interpretação semântica não impede a leitura do CSV, mas impede conclusões sem base.
Para atualizar o esquema: `uv run alembic upgrade head` (migration `0007`). Os scripts de
inicialização existentes já aplicam as migrations.

`uv run pytest` inclui os testes do motor e o fluxo da API com a IA simulada. Os testes
marcados `db` exigem o PostgreSQL local de testes e recriam seu esquema; nunca aponte
`TEST_DATABASE_URL` para um banco com dados reais.
