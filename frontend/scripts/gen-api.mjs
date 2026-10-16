// Gera src/lib/api/schema.d.ts a partir do OpenAPI do back-end.
//
// Uso:
//   npm run gen:api                       -> usa NEXT_PUBLIC_API_URL (.env.local) ou http://localhost:8000
//   npm run gen:api -- http://host:8000   -> usa outra URL base
//   npm run gen:api -- ./openapi.json     -> usa um arquivo local
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const OUTPUT = resolve("src/lib/api/schema.d.ts");

function readEnvFile(file) {
  if (!existsSync(file)) return {};
  const env = {};
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (match) env[match[1]] = match[2].replace(/^["']|["']$/g, "");
  }
  return env;
}

function resolveSource(arg) {
  if (arg && existsSync(arg)) return pathToFileURL(resolve(arg));
  const base =
    arg ??
    process.env.NEXT_PUBLIC_API_URL ??
    readEnvFile(".env.local").NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  return new URL("/openapi.json", base);
}

const source = resolveSource(process.argv[2]);
console.log(`Lendo o contrato de ${source.href}`);

try {
  const ast = await openapiTS(source);
  const header =
    "// Arquivo gerado por scripts/gen-api.mjs a partir do OpenAPI do back-end.\n" +
    "// Não edite à mão: rode `npm run gen:api`.\n\n";
  writeFileSync(OUTPUT, header + astToString(ast));
  console.log(`Tipos gravados em ${OUTPUT}`);
} catch (error) {
  console.error(`Não foi possível gerar os tipos: ${error.message}`);
  console.error("Confira se o back-end está rodando e se a URL está correta.");
  process.exit(1);
}
