// Sobe o Postgres de dev (se ainda não estiver de pé), aplica as migrations e inicia a API.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const cwd = join(import.meta.dirname, "..", "backend");
const bin = join(cwd, ".venv", process.platform === "win32" ? "Scripts" : "bin");

if (!existsSync(bin)) {
  console.error("backend/.venv não encontrado — rode `uv sync` em backend/ primeiro.");
  process.exit(1);
}

function run(cmd, args) {
  const { status } = spawnSync(cmd, args, { cwd, stdio: "inherit" });
  if (status !== 0) process.exit(status ?? 1);
}

run("docker", ["compose", "-f", "docker-compose.dev.yml", "up", "-d", "--wait"]);
run(join(bin, "alembic"), ["upgrade", "head"]);
run(join(bin, "uvicorn"), ["app.main:app", "--reload"]);
