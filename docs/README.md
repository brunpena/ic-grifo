# Documentação do IC Grifo

Este material descreve o comportamento implementado no repositório. Os caminhos nos
diagramas e nas tabelas levam aos arquivos que executam cada etapa. Os diagramas usam
Mermaid e podem ser lidos diretamente no GitHub ou em um visualizador Markdown com
suporte a Mermaid.

## Ordem sugerida

1. [Roteiro de leitura](roteiro-de-leitura.md): uma sequência para abrir o código sem se perder.
2. [Arquitetura](arquitetura.md): conceitos, camadas, persistência e relações.
3. [Fluxos](fluxos.md): operações explicadas por etapas e diagramas.
4. [Backend](backend.md) e [frontend](frontend.md): função de cada arquivo mantido nessas partes.
5. [Validação](validacao.md): exemplo completo, critérios e resultados.
6. [API](api.md): endpoints e contratos usados pela interface.
7. [Desenvolvimento](desenvolvimento.md): ambiente, comandos, configurações e diagnóstico.

## Encontre uma resposta

| Pergunta | Documento e trecho para procurar |
| --- | --- |
| O que é uma análise? | Arquitetura: vocabulário e modelo de dados |
| Por que um documento HTML aparece como PDF? | Fluxos: entrada e processamento de documentos |
| Quem calcula os grifos? | Backend: `pdf_text.py` e `highlights.py` |
| Onde ficam as linhas do CSV? | Arquitetura: divisão entre banco, arquivos e memória |
| A IA calcula cada registro? | Validação: interpretação, plano e execução |
| Por que uma regra está inconclusiva? | Validação: evidência insuficiente e prioridade dos resultados |
| Validar uma regra manualmente muda a conformidade? | Validação: revisão humana e cumprimento |
| Como a interface acompanha tarefas? | Frontend: consultas, polling e cache |
| O chat pesquisa todos os documentos? | Fluxos: conversa restrita ao documento aberto |
| A Base de regras já é uma busca semântica? | Arquitetura: implementado e demonstrativo |
| Onde alterar um endpoint? | API e mapa do backend |
| Quais arquivos são gerados? | Mapas do frontend e guia de desenvolvimento |
| Como testar sem usar a IA real? | Desenvolvimento: testes e banco dedicado |

## Documentação próxima ao código

- [README da raiz](../README.md): apresentação e ponto de entrada.
- [README do backend](../backend/README.md): comandos e navegação do servidor.
- [README do frontend](../frontend/README.md): comandos e geração dos tipos.
- [Guia operacional da validação](../backend/VALIDACAO.md): resumo da funcionalidade junto ao backend.

## Como manter este material

Ao mudar uma rota, atualize a referência da API e gere novamente os tipos TypeScript.
Ao criar ou mover um arquivo, atualize seu mapa. Ao mudar uma transição de estado,
atualize os fluxogramas e a descrição do resultado. As referências usam nomes de funções
em vez de números de linha para resistir melhor às edições.

Não use comentários antigos como prova de que uma funcionalidade está ativa. A seção
sobre limites da arquitetura registra estruturas preparadas para o futuro e diferenças
já identificadas entre comentários e implementação.
