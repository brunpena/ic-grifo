// Confere se todo texto marcado para tradução tem versão em inglês.
// Chaves: 1º argumento de t("..."), msg("...") e os dois textos de t.plural(n, "...", "...").
// Uso: npm run i18n:check   (sai com código 1 se faltar alguma chave). O Node lê o en.ts
// direto, removendo os tipos (--experimental-strip-types, Node 22.6+).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src", import.meta.url));
const STRING = String.raw`("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\x60[^\x60$]*\x60)`;
const SINGLE = new RegExp(String.raw`\b(?:t|msg)\(\s*${STRING}`, "g");
const PLURAL = new RegExp(String.raw`\bt\.plural\([^,]+,\s*${STRING}\s*,\s*${STRING}`, "g");

const parse = (literal) =>
  literal[0] === '"' ? JSON.parse(literal) : literal.slice(1, -1).replace(/\\'/g, "'");

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* files(path);
    else if (/\.tsx?$/.test(name) && !path.includes(join("lib", "i18n"))) yield path;
  }
}

const { en } = await import(new URL("../src/lib/i18n/en.ts", import.meta.url));
const used = new Map();
for (const path of files(root)) {
  const source = readFileSync(path, "utf8");
  for (const match of source.matchAll(SINGLE)) used.set(parse(match[1]), relative(root, path));
  for (const match of source.matchAll(PLURAL)) {
    used.set(parse(match[1]), relative(root, path));
    used.set(parse(match[2]), relative(root, path));
  }
}

const missing = [...used].filter(([key]) => !(key in en));
const vars = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
const wrongVars = [...used.keys()].filter((key) => key in en && vars(key) !== vars(en[key]));
const unused = Object.keys(en).filter((key) => !used.has(key));

for (const [key, file] of missing) console.log(`faltando  ${file}: ${JSON.stringify(key)}`);
for (const key of wrongVars) console.log(`variáveis diferentes: ${JSON.stringify(key)} → ${JSON.stringify(en[key])}`);
for (const key of unused) console.log(`sem uso   ${JSON.stringify(key)}`);
console.log(`${used.size} textos; ${missing.length} sem tradução; ${wrongVars.length} com variáveis diferentes; ${unused.length} sem uso.`);
process.exit(missing.length || wrongVars.length ? 1 : 0);
