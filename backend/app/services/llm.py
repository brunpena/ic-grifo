"""Chamadas ao Gemini (API REST do Google AI Studio): extração de regras e conversa."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.db.models import RULE_TYPES

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
# Respostas 429 (cota do plano gratuito) e 5xx (modelo sobrecarregado) são refeitas.
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
CONNECTION_ERROR = "Não foi possível falar com a API do Gemini. Verifique a conexão do servidor."
BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "OTHER"}


class LlmUnavailableError(Exception):
    """Sem chave da API configurada."""


class LlmApiError(Exception):
    """Falha da API do Gemini, com mensagem em português para a pessoa."""


def ensure_configured() -> str:
    key = get_settings().gemini_api_key.get_secret_value()
    if not key:
        raise LlmUnavailableError("Configure GEMINI_API_KEY no .env do back-end para usar a IA.")
    return key


def friendly_error(status: int, body: str) -> str:
    """Mensagem em português para os erros da API que a pessoa consegue resolver."""
    lower = body.lower()
    if "api key not valid" in lower or "api_key_invalid" in lower:
        return "A chave do Gemini é inválida. Confira GEMINI_API_KEY no .env do back-end."
    if status == 429 and _daily_quota(body):
        return (
            "A cota diária do Gemini para este modelo acabou. Tente amanhã, troque "
            "GEMINI_MODEL no .env (cada modelo tem cota própria) ou ative o faturamento."
        )
    if status == 429:
        return (
            "Limite de uso gratuito do Gemini atingido. Espere um minuto e tente de novo "
            "(ou diminua LLM_MAX_CONCURRENCY no .env)."
        )
    if status == 404:
        return "Modelo do Gemini não encontrado. Confira GEMINI_MODEL no .env do back-end."
    if status == 403:
        return "A chave do Gemini não tem permissão para usar este modelo."
    if status >= 500:
        return "O Gemini está sobrecarregado agora. Tente de novo em alguns minutos."
    return "A IA não conseguiu responder agora. Tente de novo."


def _daily_quota(body: str) -> bool:
    # Cota por dia (ex.: GenerateRequestsPerDayPerProjectPerModel-FreeTier): repetir não adianta.
    return "PerDay" in body


def _retry_delay(attempt: int, body: str) -> float:
    # O 429 do Gemini costuma dizer quanto esperar ("retryDelay": "37s").
    match = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', body)
    if match:
        return min(float(match.group(1)) + 1, 60)
    return min(2 ** (attempt + 1), 30)


def _url(method: str) -> str:
    return f"{API_URL}/{get_settings().gemini_model}:{method}"


def _text(data: dict) -> tuple[str, str | None]:
    """Texto da resposta (sem as partes de raciocínio) e o motivo de parada."""
    candidates = data.get("candidates") or []
    if not candidates:
        return "", (data.get("promptFeedback") or {}).get("blockReason")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return text, candidate.get("finishReason")


async def _generate(payload: dict) -> dict:
    """generateContent com novas tentativas em limite de uso e sobrecarga."""
    key = ensure_configured()
    async with httpx.AsyncClient(timeout=180) as client:
        for attempt in range(MAX_ATTEMPTS):
            last = attempt == MAX_ATTEMPTS - 1
            try:
                response = await client.post(
                    _url("generateContent"), headers={"x-goog-api-key": key}, json=payload
                )
            except httpx.HTTPError as exc:
                if last:
                    raise LlmApiError(CONNECTION_ERROR) from exc
                await asyncio.sleep(2)
                continue
            if response.status_code == 200:
                return response.json()
            body = response.text
            if response.status_code in RETRY_STATUS and not last and not _daily_quota(body):
                await asyncio.sleep(_retry_delay(attempt, body))
                continue
            logger.warning("gemini_error", extra={"status": response.status_code})
            raise LlmApiError(friendly_error(response.status_code, body))
    raise LlmApiError(friendly_error(0, ""))


# ---------------------------------------------------------------------------
# Extração de regras
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM = """Você analisa trechos de documentos normativos em português \
(contratos, editais, regulamentos) e identifica as regras que eles contêm.

O trecho vem dividido em frases numeradas, uma por linha: "[12] texto da frase". \
Algumas frases são pedaços de uma frase maior, cortada em ";" ou ":".

Uma regra é uma frase ou oração com força normativa:
- obrigacao: algo que alguém deve fazer ("deverá", "é obrigado a", "compete à contratada").
- proibicao: algo que não pode ser feito ("é vedado", "não poderá", "fica proibido").
- prazo: um limite de tempo ou data ("em até 10 dias úteis", "vigência de 12 meses").
- condicao: uma consequência que depende de um fato ("caso haja atraso, será aplicada multa").
- outro: outra disposição normativa que não se encaixa acima (competência, definição vinculante).

Para cada regra:
- first e last: números da primeira e da última frase que formam a regra (iguais \
quando ela cabe em uma frase só). Use o menor intervalo contínuo que expressa a regra \
inteira; nunca junte frases distantes.
- summary: resumo curto em português, até 80 caracteres, começando por verbo ou \
substantivo (ex.: "Entregar relatório mensal em até 10 dias úteis").
- type: um dos tipos acima. Se a frase traz um prazo para cumprir uma obrigação, \
prefira "prazo" quando o tempo é o ponto central e "obrigacao" quando é a ação.

Ignore títulos, sumários, cabeçalhos, rodapés, numeração e texto puramente \
descritivo. Não invente regras: se o trecho não tiver nenhuma, devolva uma lista vazia."""

# Formato de schema da API do Gemini (subconjunto do OpenAPI).
EXTRACTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "rules": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "type": {"type": "STRING", "enum": list(RULE_TYPES)},
                    "first": {"type": "INTEGER"},
                    "last": {"type": "INTEGER"},
                    "summary": {"type": "STRING"},
                },
                "required": ["type", "first", "last", "summary"],
                "propertyOrdering": ["type", "first", "last", "summary"],
            },
        }
    },
    "required": ["rules"],
}

# Uma regra com mais frases do que isso é quase sempre um intervalo errado.
MAX_RULE_SENTENCES = 8

# Fim de frase (ou de oração em ";" e ":") seguido de espaço, ou fim de parágrafo.
_SENTENCE_END = re.compile(r"[.;:!?](?=\s)|\n[ \t]*\n")


@dataclass
class ExtractedRule:
    """Regra com a posição (offsets em code points) no texto completo do documento."""

    type: str
    start: int
    end: int
    summary: str


@dataclass
class Sentence:
    start: int
    end: int


def split_sentences(text: str) -> list[Sentence]:
    """Frases do texto, com offsets. Os números delas são o que a IA devolve."""
    sentences: list[Sentence] = []
    start = 0
    for match in [*_SENTENCE_END.finditer(text), None]:
        end = match.end() if match else len(text)
        piece = text[start:end]
        stripped = piece.strip()
        if stripped:
            first = start + len(piece) - len(piece.lstrip())
            sentences.append(Sentence(first, first + len(stripped)))
        start = end
    return sentences


def split_chunks(sentences: list[Sentence], size: int, overlap: int) -> list[range]:
    """Agrupa as frases em blocos de até `size` caracteres, repetindo ~`overlap` no início
    do bloco seguinte (uma regra de várias frases pode cair na divisa)."""
    chunks: list[range] = []
    first = 0
    while first < len(sentences):
        last, length = first, 0
        while last < len(sentences):
            sentence = sentences[last]
            length += sentence.end - sentence.start
            if length > size and last > first:
                break
            last += 1
        chunks.append(range(first, last))
        if last >= len(sentences):
            break
        back, covered = last, 0
        while back > first + 1 and covered < overlap:
            back -= 1
            covered += sentences[back].end - sentences[back].start
        first = back
    return chunks


def numbered(text: str, sentences: list[Sentence], ids: range) -> str:
    """Frases do bloco, uma por linha e numeradas a partir de 1 no documento inteiro."""
    return "\n".join(
        f"[{i + 1}] {' '.join(text[sentences[i].start : sentences[i].end].split())}" for i in ids
    )


async def extract_rules_from_chunk(
    text: str, sentences: list[Sentence], ids: range
) -> list[ExtractedRule]:
    settings = get_settings()
    config: dict = {
        "temperature": 0,
        "maxOutputTokens": 16000,
        "responseMimeType": "application/json",
        "responseSchema": EXTRACTION_SCHEMA,
    }
    if settings.gemini_thinking_level:
        config["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
    data = await _generate(
        {
            "systemInstruction": {"parts": [{"text": EXTRACTION_SYSTEM}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"<trecho>\n{numbered(text, sentences, ids)}\n</trecho>"}],
                }
            ],
            "generationConfig": config,
        }
    )
    answer, finish = _text(data)
    if finish != "STOP":
        logger.warning("llm_finish", extra={"chunk_first": ids.start, "reason": finish})
    try:
        rules = json.loads(answer)["rules"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("llm_invalid_json", extra={"chunk_first": ids.start})
        return []
    result: list[ExtractedRule] = []
    for r in rules:
        if r.get("type") not in RULE_TYPES or not str(r.get("summary") or "").strip():
            continue
        try:
            first, last = sorted((int(r["first"]) - 1, int(r["last"]) - 1))
        except (KeyError, TypeError, ValueError):
            continue
        if first not in ids or last not in ids or last - first >= MAX_RULE_SENTENCES:
            logger.info("rule_out_of_range", extra={"first": first + 1, "last": last + 1})
            continue
        result.append(
            ExtractedRule(
                r["type"], sentences[first].start, sentences[last].end, r["summary"].strip()
            )
        )
    return result


async def extract_rules(
    text: str,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[ExtractedRule]:
    """Extrai regras de todos os blocos, em paralelo (até LLM_MAX_CONCURRENCY ao mesmo tempo)."""
    ensure_configured()
    settings = get_settings()
    sentences = split_sentences(text)
    chunks = split_chunks(sentences, settings.llm_chunk_chars, settings.llm_chunk_overlap)
    semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
    done = 0
    lock = asyncio.Lock()

    async def run(ids: range) -> list[ExtractedRule]:
        nonlocal done
        async with semaphore:
            rules = await extract_rules_from_chunk(text, sentences, ids)
        async with lock:
            done += 1
            if on_progress:
                await on_progress(done, len(chunks))
        return rules

    tasks = [asyncio.ensure_future(run(c)) for c in chunks]
    try:
        results = await asyncio.gather(*tasks)
    except BaseException:
        # O gather repassa o primeiro erro mas deixa os outros blocos rodando, e cada
        # um continuaria gastando cota da API à toa.
        for task in tasks:
            task.cancel()
        raise
    return [item for batch in results for item in batch]


# ---------------------------------------------------------------------------
# Conversa
# ---------------------------------------------------------------------------

CHAT_SYSTEM = """Você é o Grifo, assistente que ajuda a revisar documentos normativos \
(contratos, editais, regulamentos). Responda em português, de forma direta e curta, \
usando só o que está no documento abaixo. Se a resposta não estiver no documento, \
diga isso claramente em vez de supor.

Quando sua resposta se apoiar em uma das regras listadas, cite o identificador dela \
entre colchetes logo depois da frase, por exemplo: "O relatório é mensal [R3]." Cite \
apenas identificadores que existem na lista. Mencione a página quando ajudar a pessoa \
a encontrar o trecho. Não use títulos nem tabelas; listas curtas são aceitáveis."""


def document_context(title: str, pages: list[tuple[int, str]], rules: list[tuple[str, str]]) -> str:
    """Documento paginado e a lista de regras numeradas (R1, R2...), para o system prompt."""
    body = "\n\n".join(f"[Página {n}]\n{text}" for n, text in pages)
    rule_lines = "\n".join(f"{ref} {line}" for ref, line in rules) or "(nenhuma regra identificada)"
    return (
        f'<documento titulo="{title}">\n{body}\n</documento>\n\n<regras>\n{rule_lines}\n</regras>'
    )


async def stream_chat(context: str, history: list[dict]) -> AsyncIterator[str]:
    """Gera a resposta em pedaços de texto (streaming por SSE da API do Gemini)."""
    key = ensure_configured()
    payload = {
        "systemInstruction": {"parts": [{"text": f"{CHAT_SYSTEM}\n\n{context}"}]},
        "contents": [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in history
        ],
        "generationConfig": {"maxOutputTokens": 8000},
    }
    async with httpx.AsyncClient(timeout=180) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with client.stream(
                    "POST",
                    _url("streamGenerateContent"),
                    params={"alt": "sse"},
                    headers={"x-goog-api-key": key},
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode(errors="replace")
                        if response.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                            await asyncio.sleep(_retry_delay(attempt, body))
                            continue
                        logger.warning("gemini_error", extra={"status": response.status_code})
                        raise LlmApiError(friendly_error(response.status_code, body))
                    finish = None
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        text, reason = _text(json.loads(line[5:]))
                        finish = reason or finish
                        if text:
                            yield text
                    if finish in BLOCKED:
                        yield "\n\nNão consigo responder a essa pergunta."
                    return
            except httpx.HTTPError as exc:
                raise LlmApiError(CONNECTION_ERROR) from exc
