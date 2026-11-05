/**
 * Nomes das colunas de cada base, guardados assim que a análise é lida (o servidor já
 * detectou o cabeçalho no processamento inicial). Os skeletons das tabelas mostram esses
 * nomes enquanto os registros ainda estão chegando; depois entra só o conteúdo.
 */

const PREFIX = "dataset-columns:";
const memory = new Map<string, string[]>();

export function rememberColumns(datasetId: string, names: string[]) {
  if (!names.length) return;
  const previous = memory.get(datasetId);
  if (previous && previous.length === names.length && previous.every((n, i) => n === names[i])) return;
  memory.set(datasetId, names);
  try {
    localStorage.setItem(PREFIX + datasetId, JSON.stringify(names));
  } catch {
    // Sem localStorage (aba privada, cota cheia): fica só na memória desta sessão.
  }
}

export function knownColumns(datasetId: string | null | undefined): string[] | null {
  if (!datasetId) return null;
  const cached = memory.get(datasetId);
  if (cached) return cached;
  try {
    const stored = localStorage.getItem(PREFIX + datasetId);
    const parsed: unknown = stored ? JSON.parse(stored) : null;
    if (Array.isArray(parsed) && parsed.every((n) => typeof n === "string")) {
      memory.set(datasetId, parsed);
      return parsed;
    }
  } catch {
    // Valor corrompido ou sem acesso ao storage: o skeleton usa colunas genéricas.
  }
  return null;
}
