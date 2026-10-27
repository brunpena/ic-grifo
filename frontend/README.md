# IC Grifo — frontend

Interface Next.js, React e TypeScript do Grifo. O Assistente se conecta à API FastAPI
para documentos, CSVs, revisão, buscas, validação e conversa.

## Documentação para estudar o código

- [Roteiro de leitura](../docs/roteiro-de-leitura.md)
- [Arquitetura](../docs/arquitetura.md)
- [Fluxogramas](../docs/fluxos.md)
- [Mapa de cada arquivo do frontend](../docs/frontend.md)
- [API e hooks consumidores](../docs/api.md)
- [Validação com exemplos](../docs/validacao.md)

Comece em [layout.tsx](src/app/layout.tsx),
[providers.tsx](src/app/providers.tsx) e
[assistant-view.tsx](src/components/assistant/assistant-view.tsx).

A tela /regras e a galeria /dev/ui ainda usam demonstrações locais.
O fluxo real de processamento está no Assistente.

## Executar localmente

Prepare Node/npm e mantenha a API em execução. Os comandos começam nesta pasta:

```powershell
if (-not (Test-Path -LiteralPath .env.local)) {
    Copy-Item -LiteralPath .env.example -Destination .env.local
}
npm ci
npm run dev
```

A interface abre em http://localhost:3000.
NEXT_PUBLIC_API_URL aponta para a base da API, por exemplo http://localhost:8000,
sem /api/v1 no final. Confira o [guia completo](../docs/desenvolvimento.md).

## Tipos da API

[Schema TypeScript](src/lib/api/schema.d.ts) é gerado do OpenAPI do backend.
Não edite esse arquivo manualmente.

```powershell
npm run gen:api
npm run gen:api -- http://localhost:8000
npm run gen:api -- ./openapi.json
```

A última forma exige um arquivo OpenAPI local existente. O cliente em src/lib/api usa
openapi-fetch e unwrap para devolver dados ou lançar ApiError. Os hooks em src/lib
coordenam consultas, cache e atualizações de cada família de recursos.

## Scripts

| Comando | Função |
| --- | --- |
| npm run dev | Servidor de desenvolvimento. |
| npm run build | Build de produção. |
| npm run start | Executa um build de produção já criado. |
| npm run typecheck | Verifica tipos com TypeScript. |
| npm run lint | Executa ESLint. |
| npm run gen:api | Atualiza o contrato TypeScript pelo OpenAPI. |
