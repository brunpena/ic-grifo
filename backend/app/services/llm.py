"""Chamadas ao Gemini (API REST do Google AI Studio): extração de regras e conversa."""

import asyncio
import json
import logging
import random
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings
from app.db.models import RULE_TYPES

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
# Respostas 429 (cota do plano gratuito) e 5xx (modelo sobrecarregado) são refeitas.
RETRY_STATUS = {429, 500, 502, 503, 504}
# O 503 de sobrecarga volta em ~1 s; picos curtos passam em menos de um minuto.
MAX_ATTEMPTS = 6
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
    # Com jitter, para os blocos em paralelo não voltarem todos no mesmo instante.
    return min(2 ** (attempt + 1), 20) * random.uniform(0.5, 1.0)


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


async def _post_hedged(client: httpx.AsyncClient, key: str, payload: dict) -> httpx.Response:
    """Uma tentativa de generateContent. Sob carga a mesma requisição leva de 15 s a mais
    de 2 min; passados LLM_HEDGE_SECONDS sem resposta, manda outra igual e fica com a
    primeira que der certo."""
    hedge = get_settings().llm_hedge_seconds

    def send() -> asyncio.Future[httpx.Response]:
        return asyncio.ensure_future(
            client.post(_url("generateContent"), headers={"x-goog-api-key": key}, json=payload)
        )

    pending = {send()}
    hedged = hedge <= 0
    try:
        while True:
            done, pending = await asyncio.wait(
                pending, timeout=None if hedged else hedge, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                logger.info("gemini_hedge", extra={"after_s": hedge})
                pending.add(send())
                hedged = True
                continue
            for task in done:
                if task.exception() is None and task.result().status_code == 200:
                    return task.result()
            if not pending:
                return done.pop().result()
            hedged = True
    finally:
        for task in pending:
            task.cancel()


async def _generate(payload: dict) -> dict:
    """generateContent com novas tentativas em limite de uso e sobrecarga."""
    key = ensure_configured()
    async with httpx.AsyncClient(timeout=180) as client:
        for attempt in range(MAX_ATTEMPTS):
            last = attempt == MAX_ATTEMPTS - 1
            try:
                response = await _post_hedged(client, key, payload)
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
    # Nomes das bases de dados que têm relação com a regra (só quando há bases).
    datasets: list[str] = field(default_factory=list)


@dataclass
class DatasetPrompt:
    """O que a IA sabe de uma base: nome, tamanho e colunas (dicts de `ColumnInfo`)."""

    name: str
    row_count: int
    columns: list[dict]


TYPE_NAMES = {
    "integer": "inteiro",
    "decimal": "decimal",
    "date": "data",
    "datetime": "data e hora",
    "boolean": "sim/não",
    "text": "texto",
}


def describe_datasets(datasets: list[DatasetPrompt]) -> str:
    """Schema das bases em texto compacto, para o prompt."""
    blocks = []
    for dataset in datasets:
        lines = [f'<base nome="{dataset.name}" linhas="{dataset.row_count}">']
        for column in dataset.columns:
            kind = TYPE_NAMES.get(column["type"], column["type"])
            examples = column.get("examples") or []
            if column.get("values"):
                detail = "valores: " + " | ".join(column["values"])
            elif examples:
                detail = "ex.: " + ", ".join(examples)
            else:
                detail = "(sempre vazia)"
            lines.append(f"- {column['name']} ({kind}) {detail}")
        lines.append("</base>")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


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


def _extraction_schema(dataset_names: list[str]) -> dict:
    """Com bases na análise, cada regra diz também com quais bases ela tem relação."""
    if not dataset_names:
        return EXTRACTION_SCHEMA
    item = EXTRACTION_SCHEMA["properties"]["rules"]["items"]
    with_datasets = {
        **item,
        "properties": {
            **item["properties"],
            "datasets": {"type": "ARRAY", "items": {"type": "STRING", "enum": dataset_names}},
        },
        "required": [*item["required"], "datasets"],
        "propertyOrdering": [*item["propertyOrdering"], "datasets"],
    }
    return {**EXTRACTION_SCHEMA, "properties": {"rules": {"type": "ARRAY", "items": with_datasets}}}


def _extraction_system(datasets: list[DatasetPrompt]) -> str:
    if not datasets:
        return EXTRACTION_SYSTEM
    return f"""{EXTRACTION_SYSTEM}

As regras serão verificadas contra as bases de dados abaixo. Em `datasets`, liste as \
bases cujos registros a regra pode avaliar: a regra fala de algo que aparece nas colunas \
(valores, datas, prazos, categorias, situação). Use lista vazia quando a regra não tem \
relação com nenhuma base. Isso não muda quais regras você extrai.

<bases>
{describe_datasets(datasets)}
</bases>"""


async def extract_rules_from_chunk(
    text: str, sentences: list[Sentence], ids: range, datasets: list[DatasetPrompt] | None = None
) -> list[ExtractedRule]:
    settings = get_settings()
    datasets = datasets or []
    dataset_names = [d.name for d in datasets]
    config: dict = {
        "temperature": 0,
        "maxOutputTokens": 16000,
        "responseMimeType": "application/json",
        "responseSchema": _extraction_schema(dataset_names),
    }
    if settings.gemini_thinking_level:
        config["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
    data = await _generate(
        {
            "systemInstruction": {"parts": [{"text": _extraction_system(datasets)}]},
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
        related = [n for n in r.get("datasets") or [] if n in dataset_names]
        result.append(
            ExtractedRule(
                r["type"],
                sentences[first].start,
                sentences[last].end,
                r["summary"].strip(),
                list(dict.fromkeys(related)),
            )
        )
    return result


async def extract_rules(
    text: str,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    datasets: list[DatasetPrompt] | None = None,
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
            rules = await extract_rules_from_chunk(text, sentences, ids, datasets)
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
# Regra → busca estruturada
# ---------------------------------------------------------------------------

QUERY_OPERATORS = (
    "eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in", "contains",
    "not_contains", "starts_with", "ends_with", "is_null", "not_null",
)  # fmt: skip
# Regras por chamada: cabe folgado na resposta e poupa a cota diária.
QUERY_BATCH = 25

QUERY_SYSTEM = """Você transforma regras de documentos normativos em buscas sobre \
bases de dados em CSV. As buscas nunca são SQL: são condições sobre colunas.

Para cada regra, monte a busca que encontra os registros AOS QUAIS A REGRA SE APLICA \
(o escopo da regra), não os que a violam. Exemplo: "contratos acima de R$ 50 mil exigem \
garantia" → registros com Valor > 50000. Quem verifica se cada registro cumpre a regra \
é outra etapa.

Formato de cada busca:
- dataset: nome exato de uma das bases, ou null quando nenhuma base tem colunas para \
avaliar a regra (nesse caso, conditions vazio).
- logic: "and" (todas as condições) ou "or" (qualquer uma).
- conditions: lista de {column, op, value, values}. column é o nome exato da coluna.
- Operadores: eq (igual), ne (diferente), gt, gte, lt, lte (comparações), between \
(values = [mínimo, máximo]), in e not_in (values = lista), contains, not_contains, \
starts_with, ends_with (texto), is_null e not_null (sem valor).
- Comparações gt/gte/lt/lte/between só em colunas de número, data ou data e hora. \
Colunas sim/não aceitam só eq e ne.
- value sempre como texto: números com ponto decimal e sem milhar ("50000.00"), datas \
em AAAA-MM-DD, sim/não como "true" ou "false". Em colunas com lista de valores, use \
exatamente um dos valores listados.
- Uma regra que se aplica a todos os registros da base fica com conditions vazio.
- reason: uma frase curta explicando a busca ou por que nenhuma base serve.

Não invente colunas nem valores que não estão nas bases."""

QUERY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "queries": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "rule": {"type": "INTEGER"},
                    "dataset": {"type": "STRING", "nullable": True},
                    "logic": {"type": "STRING", "enum": ["and", "or"]},
                    "conditions": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "column": {"type": "STRING"},
                                "op": {"type": "STRING", "enum": list(QUERY_OPERATORS)},
                                "value": {"type": "STRING", "nullable": True},
                                "values": {"type": "ARRAY", "items": {"type": "STRING"}},
                            },
                            "required": ["column", "op"],
                            "propertyOrdering": ["column", "op", "value", "values"],
                        },
                    },
                    "reason": {"type": "STRING"},
                },
                "required": ["rule", "dataset", "logic", "conditions", "reason"],
                "propertyOrdering": ["rule", "dataset", "logic", "conditions", "reason"],
            },
        }
    },
    "required": ["queries"],
}


@dataclass
class RulePrompt:
    """Uma regra enviada para virar busca. `ref` é o número usado na resposta."""

    ref: int
    type: str
    summary: str
    excerpt: str


@dataclass
class GeneratedQuery:
    """A busca como a IA devolveu; ainda precisa passar pela validação do schema."""

    dataset: str | None
    query: dict
    reason: str


def _query_from_answer(item: dict) -> GeneratedQuery:
    conditions = []
    for c in item.get("conditions") or []:
        op = c.get("op")
        if op not in QUERY_OPERATORS or not str(c.get("column") or "").strip():
            continue
        if op in ("between", "in", "not_in"):
            value: object = [str(v) for v in c.get("values") or []]
        elif op in ("is_null", "not_null"):
            value = None
        else:
            value = None if c.get("value") is None else str(c.get("value"))
        column = str(c.get("column")).strip()[:200]
        conditions.append({"column": column, "op": op, "value": value})
    dataset = item.get("dataset") or None
    return GeneratedQuery(
        dataset=dataset,
        query={
            "dataset": str(dataset or "?"),
            "logic": "or" if item.get("logic") == "or" else "and",
            "conditions": conditions,
        },
        reason=str(item.get("reason") or "").strip(),
    )


async def generate_queries_batch(
    rules: list[RulePrompt], datasets: list[DatasetPrompt]
) -> dict[int, GeneratedQuery]:
    settings = get_settings()
    config: dict = {
        "temperature": 0,
        "maxOutputTokens": 16000,
        "responseMimeType": "application/json",
        "responseSchema": QUERY_SCHEMA,
    }
    if settings.gemini_thinking_level:
        config["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
    listing = "\n".join(
        f"[{r.ref}] ({r.type}) {r.summary} — “{' '.join(r.excerpt.split())}”" for r in rules
    )
    data = await _generate(
        {
            "systemInstruction": {"parts": [{"text": QUERY_SYSTEM}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": f"<bases>\n{describe_datasets(datasets)}\n</bases>\n\n"
                            f"<regras>\n{listing}\n</regras>"
                        }
                    ],
                }
            ],
            "generationConfig": config,
        }
    )
    answer, finish = _text(data)
    if finish != "STOP":
        logger.warning("llm_finish", extra={"step": "queries", "reason": finish})
    try:
        items = json.loads(answer)["queries"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("llm_invalid_json", extra={"step": "queries"})
        return {}
    refs = {r.ref for r in rules}
    result: dict[int, GeneratedQuery] = {}
    for item in items:
        try:
            ref = int(item["rule"])
        except (KeyError, TypeError, ValueError):
            continue
        if ref in refs and ref not in result:
            result[ref] = _query_from_answer(item)
    return result


async def generate_queries(
    rules: list[RulePrompt], datasets: list[DatasetPrompt]
) -> dict[int, GeneratedQuery]:
    """Buscas para todas as regras, em lotes paralelos (até LLM_MAX_CONCURRENCY)."""
    ensure_configured()
    semaphore = asyncio.Semaphore(get_settings().llm_max_concurrency)
    batches = [rules[i : i + QUERY_BATCH] for i in range(0, len(rules), QUERY_BATCH)]

    async def run(batch: list[RulePrompt]) -> dict[int, GeneratedQuery]:
        async with semaphore:
            return await generate_queries_batch(batch, datasets)

    tasks = [asyncio.ensure_future(run(b)) for b in batches]
    try:
        results = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        raise
    return {ref: query for batch in results for ref, query in batch.items()}


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
