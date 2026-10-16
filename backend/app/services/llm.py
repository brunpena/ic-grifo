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
            if response.status_code in RETRY_STATUS and not last:
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

Uma regra é uma frase ou oração com força normativa:
- obrigacao: algo que alguém deve fazer ("deverá", "é obrigado a", "compete à contratada").
- proibicao: algo que não pode ser feito ("é vedado", "não poderá", "fica proibido").
- prazo: um limite de tempo ou data ("em até 10 dias úteis", "vigência de 12 meses").
- condicao: uma consequência que depende de um fato ("caso haja atraso, será aplicada multa").
- outro: outra disposição normativa que não se encaixa acima (competência, definição vinculante).

Para cada regra:
- excerpt: copie o trecho EXATAMENTE como aparece no texto, caractere por caractere, \
sem resumir, corrigir ou juntar partes distantes. Use o menor trecho contínuo que \
expressa a regra inteira (normalmente uma oração ou frase).
- summary: resumo curto em português, até 80 caracteres, começando por verbo ou \
substantivo (ex.: "Entregar relatório mensal em até 10 dias úteis").
- type: um dos tipos acima. Se a frase traz um prazo para cumprir uma obrigação, \
prefira "prazo" quando o tempo é o ponto central e "obrigacao" quando é a ação.

Ignore títulos, sumários, cabeçalhos, rodapés, numeração e texto puramente \
descritivo. Não invente regras: se o trecho não tiver nenhuma, devolva uma lista vazia. \
O trecho pode começar ou terminar no meio de uma frase; ignore frases cortadas nas bordas."""

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
                    "excerpt": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                },
                "required": ["type", "excerpt", "summary"],
                "propertyOrdering": ["type", "excerpt", "summary"],
            },
        }
    },
    "required": ["rules"],
}


@dataclass
class ExtractedRule:
    type: str
    excerpt: str
    summary: str


@dataclass
class TextChunk:
    start: int
    text: str


def split_chunks(text: str, size: int, overlap: int) -> list[TextChunk]:
    """Divide o texto em blocos com sobreposição, cortando de preferência entre parágrafos."""
    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            # Volta até a última quebra de parágrafo (ou de linha) na metade final do bloco.
            for sep in ("\n\n", "\n", ". "):
                cut = text.rfind(sep, start + size // 2, end)
                if cut > 0:
                    end = cut + len(sep)
                    break
        chunks.append(TextChunk(start, text[start:end]))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


async def extract_rules_from_chunk(chunk: TextChunk) -> list[ExtractedRule]:
    data = await _generate(
        {
            "systemInstruction": {"parts": [{"text": EXTRACTION_SYSTEM}]},
            "contents": [
                {"role": "user", "parts": [{"text": f"<trecho>\n{chunk.text}\n</trecho>"}]}
            ],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 16000,
                "responseMimeType": "application/json",
                "responseSchema": EXTRACTION_SCHEMA,
            },
        }
    )
    text, finish = _text(data)
    if finish != "STOP":
        logger.warning("llm_finish", extra={"chunk_start": chunk.start, "reason": finish})
    try:
        rules = json.loads(text)["rules"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("llm_invalid_json", extra={"chunk_start": chunk.start})
        return []
    return [
        ExtractedRule(r["type"], r["excerpt"], r["summary"].strip())
        for r in rules
        if r.get("type") in RULE_TYPES and r.get("excerpt") and r.get("summary")
    ]


async def extract_rules(
    text: str,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[tuple[TextChunk, ExtractedRule]]:
    """Extrai regras de todos os blocos, em paralelo (até LLM_MAX_CONCURRENCY ao mesmo tempo)."""
    ensure_configured()
    settings = get_settings()
    chunks = split_chunks(text, settings.llm_chunk_chars, settings.llm_chunk_overlap)
    semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
    done = 0
    lock = asyncio.Lock()

    async def run(chunk: TextChunk) -> list[tuple[TextChunk, ExtractedRule]]:
        nonlocal done
        async with semaphore:
            rules = await extract_rules_from_chunk(chunk)
        async with lock:
            done += 1
            if on_progress:
                await on_progress(done, len(chunks))
        return [(chunk, rule) for rule in rules]

    results = await asyncio.gather(*(run(c) for c in chunks))
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
