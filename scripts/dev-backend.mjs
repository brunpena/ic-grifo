// Sobe o Postgres de dev (se o banco for local), aplica as migrations e inicia a API.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { delimiter, join } from "node:path";

const cwd = join(import.meta.dirname, "..", "backend");
const bin = join(cwd, ".venv", process.platform === "win32" ? "Scripts" : "bin");

if (!existsSync(bin)) {
  console.error("backend/.venv não encontrado — rode `uv sync` em backend/ primeiro.");
  process.exit(1);
}

function run(cmd, args) {
  const { status, error } = spawnSync(cmd, args, { cwd, stdio: "inherit" });
  if (error) {
    console.error(`Falha ao executar \`${cmd}\`: ${error.message}`);
    if (error.code === "ENOENT") console.error("Verifique se está instalado e no PATH (reabra o terminal após instalar).");
    process.exit(1);
  }
  if (status !== 0) {
    console.error(`\`${cmd} ${args.join(" ")}\` saiu com código ${status}.`);
    process.exit(status ?? 1);
  }
}

// O Postgres do docker-compose.dev.yml só é necessário quando o banco é local; com o
// Supabase (DATABASE_URL remoto) o Docker nem precisa estar instalado.
function databaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  const envFile = join(cwd, ".env");
  if (!existsSync(envFile)) return "";
  const line = readFileSync(envFile, "utf8")
    .split(/\r?\n/)
    .find((l) => /^\s*DATABASE_URL\s*=/.test(l));
  return line ? line.split("=").slice(1).join("=").trim().replace(/^["']|["']$/g, "") : "";
}

const url = databaseUrl();
// Sem DATABASE_URL vale o padrão do config.py, que é o banco local.
if (!url || /@(localhost|127\.0\.0\.1)(:|\/)/.test(url)) {
  run("docker", ["compose", "-f", "docker-compose.dev.yml", "up", "-d", "--wait"]);
}
run(join(bin, "alembic"), ["upgrade", "head"]);
// Reload pelo watchfiles em vez do `uvicorn --reload`: no Windows o reloader do uvicorn
// reinicia mandando Ctrl+C para o console inteiro, o que derruba o Next e o `npm run dev`.
process.env.PATH = `${bin}${delimiter}${process.env.PATH}`;
run(join(bin, "watchfiles"), ["--filter", "python", "uvicorn app.main:app", "app"]);
