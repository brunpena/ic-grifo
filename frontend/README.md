# IC Grifo: front-end

Interface (Next.js + TypeScript) do sistema de validação de regras em documentos.
A documentação completa entra na etapa final. Por enquanto:

## Rodando localmente

Pré-requisitos: Node.js 20+ e o back-end rodando (ver `../backend/README.md`).

```bash
cd frontend
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                  # http://localhost:3000
```

## Tipos da API

Os tipos em `src/lib/api/schema.d.ts` são gerados a partir do OpenAPI do back-end.
Rode de novo sempre que o contrato mudar:

```bash
npm run gen:api                          # usa NEXT_PUBLIC_API_URL (ou http://localhost:8000)
npm run gen:api -- https://api.exemplo   # outra URL base
npm run gen:api -- ./openapi.json        # arquivo local
```

O cliente tipado fica em `src/lib/api`: `api.GET("/api/v1/...")` com `unwrap(...)` devolve
os dados ou lança um `ApiError` com a mensagem em português vinda do back.

## Scripts

- `npm run dev`: servidor de desenvolvimento
- `npm run build`: build de produção
- `npm run typecheck`: checagem de tipos (TypeScript strict)
- `npm run lint`: ESLint
