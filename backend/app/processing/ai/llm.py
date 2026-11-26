"""Chamadas ao Gemini (API REST do Google AI Studio): análise de trechos grifados e conversa."""

import asyncio
import json
import logging
import random
import re
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from weakref import WeakKeyDictionary

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


class _RequestLimiter:
    """Budget shared by all documents, retries and streams on this event loop."""

    def __init__(self, concurrency: int, rate: int, *, window: float = 60.0):
        self.concurrency = concurrency
        self.rate = rate
        self.window = window
        self.active = 0
        self.waiters = 0
        self.starts: deque[float] = deque()
        self.changed = asyncio.Condition()

    async def acquire(self, *, wait: bool = True) -> bool:
        async with self.changed:
            if not wait and self.waiters:
                return False
            while True:
                now = asyncio.get_running_loop().time()
                while self.starts and self.starts[0] <= now - self.window:
                    self.starts.popleft()
                if self.active < self.concurrency and len(self.starts) < self.rate:
                    self.active += 1
                    self.starts.append(now)
                    return True
                if not wait:
                    return False
                delay = (
                    self.starts[0] + self.window - now if len(self.starts) >= self.rate else None
                )
                self.waiters += 1
                try:
                    await asyncio.wait_for(self.changed.wait(), timeout=delay)
                except TimeoutError:
                    pass
                finally:
                    self.waiters -= 1

    async def release(self) -> None:
        async with self.changed:
            self.active -= 1
            self.changed.notify_all()


_limiters: WeakKeyDictionary[asyncio.AbstractEventLoop, _RequestLimiter] = WeakKeyDictionary()


def _request_limiter() -> _RequestLimiter:
    loop = asyncio.get_running_loop()
    settings = get_settings()
    concurrency = max(1, settings.llm_max_concurrency)
    rate = max(1, settings.llm_rate_limit_per_minute)
    limiter = _limiters.get(loop)
    if limiter is None:
        limiter = _RequestLimiter(concurrency, rate)
        _limiters[loop] = limiter
    else:
        limiter.concurrency = concurrency
        limiter.rate = rate
    return limiter


@asynccontextmanager
async def _request_slot():
    limiter = _request_limiter()
    await limiter.acquire()
    try:
        yield
    finally:
        await limiter.release()


class LlmUnavailableError(Exception):
    """Sem chave da API configurada."""


class LlmApiError(Exception):
    """Falha da API do Gemini, com mensagem em português para a pessoa."""


_key_cooldowns: dict[tuple[str, str], tuple[float, str]] = {}
_key_cursor = 0


def _configured_keys() -> list[str]:
    settings = get_settings()
    keys = [
        settings.gemini_api_key.get_secret_value().strip(),
        settings.gemini_api_key_2.get_secret_value().strip(),
        settings.gemini_api_key_3.get_secret_value().strip(),
    ]
    return list(dict.fromkeys(key for key in keys if key))


def ensure_configured() -> str:
    keys = _configured_keys()
    if not keys and getattr(get_settings(), "llm_mock", False):
        return "mock"
    if not keys:
        raise LlmUnavailableError("Configure GEMINI_API_KEY no .env do back-end para usar a IA.")
    return keys[0]


def _select_key() -> str:
    global _key_cursor
    ensure_configured()
    keys = _configured_keys()
    model = get_settings().gemini_model
    for offset in range(len(keys)):
        index = (_key_cursor + offset) % len(keys)
        key = keys[index]
        if _key_cooldowns.get((model, key), (0, ""))[0] <= time.monotonic():
            _key_cursor = (index + 1) % len(keys)
            return key
    body = min((_key_cooldowns[(model, key)] for key in keys), key=lambda item: item[0])[1]
    raise LlmApiError(friendly_error(429, body))


def _quota_failover(key: str, status: int, body: str, attempt: int) -> bool:
    keys = _configured_keys()
    if status != 429 or len(keys) < 2:
        return False
    model = get_settings().gemini_model
    daily = _daily_quota(body)
    # RetryInfo de cota diária pode indicar horas até o reset. Não bloquear 24h
    # adicionais quando o Google informa uma liberação anterior.
    retry_after = _provider_retry_delay(body)
    delay = (
        ((retry_after + 1) if retry_after is not None else 24 * 60 * 60)
        if daily
        else (_retry_delay(attempt, body))
    )
    _key_cooldowns[(model, key)] = (time.monotonic() + delay, body)
    logger.warning(
        "gemini_quota_limited",
        extra={
            "model": model,
            "credential_slot": keys.index(key) + 1,
            "configured_credentials": len(keys),
            "quota_period": "day" if daily else "temporary",
            "cooldown_seconds": round(delay, 1),
        },
    )
    return any(
        candidate != key and _key_cooldowns.get((model, candidate), (0, ""))[0] <= time.monotonic()
        for candidate in keys
    )


def friendly_error(status: int, body: str) -> str:
    """Mensagem em português para os erros da API que a pessoa consegue resolver."""
    lower = body.lower()
    if "api key not valid" in lower or "api_key_invalid" in lower:
        return "A chave do Gemini é inválida. Confira GEMINI_API_KEY no .env do back-end."
    if status == 429 and _daily_quota(body):
        return (
            "O Google informou limite de cota diária para este modelo nas credenciais "
            "disponíveis. Chaves do mesmo projeto compartilham a cota. Confira os limites "
            "do projeto no Google AI Studio e aguarde a liberação informada pelo provedor."
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


def _provider_retry_delay(body: str) -> float | None:
    """RetryInfo em segundos, sem reduzir o prazo diário ao backoff de 60 segundos."""
    match = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', body)
    return float(match.group(1)) if match else None


def _retry_delay(attempt: int, body: str) -> float:
    # O 429 do Gemini costuma dizer quanto esperar ("retryDelay": "37s").
    delay = _provider_retry_delay(body)
    if delay is not None:
        return min(delay + 1, 60)
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
    limiter = _request_limiter()

    async def send() -> httpx.Response:
        return await client.post(
            _url("generateContent"), headers={"x-goog-api-key": key}, json=payload
        )

    # Start the hedge clock only after the original request has a budget slot.
    await limiter.acquire()
    pending = {asyncio.create_task(send())}
    tasks = set(pending)
    reservations = 1
    hedged = hedge <= 0
    try:
        while True:
            done, pending = await asyncio.wait(
                pending, timeout=None if hedged else hedge, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                # Speculative work must not queue behind real requests or exceed quota.
                if await limiter.acquire(wait=False):
                    reservations += 1
                    logger.info("gemini_hedge", extra={"after_s": hedge})
                    task = asyncio.create_task(send())
                    pending.add(task)
                    tasks.add(task)
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
        await asyncio.gather(*tasks, return_exceptions=True)
        for _ in range(reservations):
            await limiter.release()


async def _generate(payload: dict) -> dict:
    """generateContent com novas tentativas em limite de uso e sobrecarga."""
    ensure_configured()
    async with httpx.AsyncClient(timeout=180) as client:
        for attempt in range(MAX_ATTEMPTS):
            key = _select_key()
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
            if _quota_failover(key, response.status_code, body, attempt) and not last:
                continue
            if response.status_code in RETRY_STATUS and not last and not _daily_quota(body):
                await asyncio.sleep(_retry_delay(attempt, body))
                continue
            logger.warning("gemini_error", extra={"status": response.status_code})
            raise LlmApiError(friendly_error(response.status_code, body))
    raise LlmApiError(friendly_error(0, ""))


# ---------------------------------------------------------------------------
# Bases de dados no prompt
# ---------------------------------------------------------------------------


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
            semantic = column.get("semantic")
            if semantic:
                detail += (
                    f"; significado: {semantic['meaning']}"
                    f"; confiança: {semantic['confidence']}"
                    f"; evento: {semantic.get('event')}; unidade: {semantic.get('unit')}"
                )
            lines.append(f"- {column['name']} ({kind}) {detail}")
        lines.append("</base>")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


@dataclass
class RulePrompt:
    """Uma regra enviada à IA (plano de validação). `ref` é o número usado na resposta."""

    ref: int
    type: str
    summary: str
    excerpt: str


# ---------------------------------------------------------------------------
# Trecho grifado → proposta de regra (conversa guiada pela pessoa)
# ---------------------------------------------------------------------------

QUERY_OPERATORS = (
    "eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in", "contains",
    "not_contains", "starts_with", "ends_with", "is_null", "not_null",
)  # fmt: skip

# Texto da página em volta do trecho, para a IA entender o contexto sem ler o documento todo.
EXCERPT_CONTEXT_CHARS = 6000
# Regras já aprovadas no documento, resumidas (histórico para a IA manter a coerência).
PREVIOUS_RULES_CHARS = 8000

PREVIOUS_RULES_NOTE = """Em <regras_anteriores> estão as regras já aprovadas neste \
documento. Use-as para manter a mesma leitura e os mesmos critérios (colunas, valores, \
tipo). Se o trecho grifado repete, detalha ou contradiz uma delas, diga isso no reply. \
Não analise as regras anteriores de novo nem as altere: o foco é o trecho grifado."""

EXCERPT_SYSTEM = (
    """Você é o Grifo, assistente que ajuda uma pessoa a transformar \
trechos de documentos normativos (editais, portarias, contratos, regulamentos) em \
regras verificáveis. A pessoa grifou um trecho do documento; você analisa SOMENTE esse \
trecho, usando o texto da página apenas como contexto. Nada do que você propõe é salvo \
sem a aprovação dela.

Em toda resposta, devolva:
- reply: sua mensagem para a pessoa, em português, curta e direta (até 5 frases). \
Explique a interpretação, por que a regra pode ou não ser verificada nos dados e o que \
a busca encontra. Responda perguntas e aplique os ajustes pedidos.
- is_rule: true se o trecho tem força normativa (obrigação, proibição, prazo, condição \
ou outra disposição vinculante); false se é só título, ementa, definição sem efeito ou \
texto descritivo.
- verifiable: true somente se as colunas das bases permitem encontrar os registros aos \
quais a regra se aplica. Se faltam colunas, se elas são ambíguas ou se a regra trata de \
algo que não está nos registros (assinatura de termo, publicação, vigência), false.
- type: obrigacao, proibicao, prazo, condicao ou outro.
- summary: resumo da regra em uma frase (até 150 caracteres), no infinitivo quando couber.
- interpretation: como a regra deve ser lida, quem ela atinge e quais colunas (se houver) \
representam cada elemento dela.
- reason: uma frase dizendo por que é ou não verificável nos dados.
- dataset, logic, conditions: a busca, só quando verifiable = true; caso contrário \
dataset null e conditions vazio.

A busca encontra os registros AOS QUAIS A REGRA SE APLICA (o escopo da regra), não os \
que a violam. Exemplo: "contratos acima de R$ 50 mil exigem garantia" → registros com \
Valor > 50000. As buscas nunca são SQL livre: são condições sobre colunas que o \
backend compila em SQL parametrizado.
- dataset: nome exato de uma das bases.
- logic: "and" (todas as condições) ou "or" (qualquer uma).
- conditions: lista de {column, op, value, values}. column é o nome exato da coluna.
- Operadores: eq, ne, gt, gte, lt, lte, between (values = [mínimo, máximo]), in e \
not_in (values = lista), contains, not_contains, starts_with, ends_with (texto), \
is_null e not_null (sem valor).
- gt/gte/lt/lte/between só em colunas de número, data ou data e hora. Colunas sim/não \
aceitam só eq e ne.
- value sempre como texto: números com ponto decimal e sem milhar ("50000.00"), datas \
em AAAA-MM-DD, sim/não como "true" ou "false". Em colunas com lista de valores, use \
exatamente um dos valores listados.
- Uma regra que se aplica a todos os registros da base fica com conditions vazio.

Use os significados, eventos e unidades já interpretados das colunas. Não trate \
assinatura, publicação, realização ou vencimento como datas equivalentes. Não invente \
colunas nem valores. Quando houver uma <proposta_atual>, parta dela: a pessoa pode tê-la \
editado à mão. Mantenha o que ela não pediu para mudar.

"""
    + PREVIOUS_RULES_NOTE
)

EXCERPT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "reply": {"type": "STRING"},
        "is_rule": {"type": "BOOLEAN"},
        "verifiable": {"type": "BOOLEAN"},
        "type": {"type": "STRING", "enum": list(RULE_TYPES)},
        "summary": {"type": "STRING"},
        "interpretation": {"type": "STRING"},
        "reason": {"type": "STRING"},
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
    },
    "required": [
        "reply", "is_rule", "verifiable", "type", "summary", "interpretation", "reason",
        "dataset", "logic", "conditions",
    ],
    "propertyOrdering": [
        "reply", "is_rule", "verifiable", "type", "summary", "interpretation", "reason",
        "dataset", "logic", "conditions",
    ],
}  # fmt: skip


@dataclass
class ExcerptPrompt:
    """O trecho grifado e o que a IA precisa para analisá-lo."""

    excerpt: str
    page: int
    # Texto da página (ou de parte dela) em volta do trecho.
    context: str
    datasets: list[DatasetPrompt]
    # Conversa até aqui: [{role: user|assistant, content}], terminando na pessoa.
    history: list[dict]
    # Proposta atual (possivelmente editada pela pessoa), no formato de `ExcerptAnswer`.
    current: dict | None = None
    # Regras já aprovadas no documento, uma por item, em texto.
    previous_rules: list[str] = field(default_factory=list)


def _previous_block(prompt: ExcerptPrompt) -> str:
    rules = "\n".join(prompt.previous_rules) or "(nenhuma regra aprovada ainda)"
    return f"<regras_anteriores>\n{rules}\n</regras_anteriores>\n\n"


@dataclass
class ExcerptAnswer:
    """A resposta da IA como veio; a busca ainda passa pela validação do schema."""

    reply: str
    is_rule: bool
    verifiable: bool
    type: str
    summary: str
    interpretation: str
    reason: str
    # Busca no formato de StructuredQuery, ou None quando a regra não é verificável.
    query: dict | None


def query_from_answer(item: dict) -> dict | None:
    """Converte {dataset, logic, conditions} da IA em StructuredQuery (sem validar colunas)."""
    dataset = str(item.get("dataset") or "").strip()
    if not dataset:
        return None
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
    return {
        "dataset": dataset[:200],
        "logic": "or" if item.get("logic") == "or" else "and",
        "conditions": conditions,
    }


def _excerpt_answer(item: dict) -> ExcerptAnswer:
    verifiable = bool(item.get("verifiable")) and bool(item.get("is_rule", True))
    kind = item.get("type") if item.get("type") in RULE_TYPES else "outro"
    return ExcerptAnswer(
        reply=str(item.get("reply") or "").strip(),
        is_rule=bool(item.get("is_rule", True)),
        verifiable=verifiable,
        type=kind,
        summary=" ".join(str(item.get("summary") or "").split())[:200],
        interpretation=str(item.get("interpretation") or "").strip()[:4000],
        reason=str(item.get("reason") or "").strip()[:1000],
        query=query_from_answer(item) if verifiable else None,
    )


def _excerpt_contents(prompt: ExcerptPrompt) -> list[dict]:
    bases = describe_datasets(prompt.datasets) if prompt.datasets else "(nenhuma base pronta)"
    opening = (
        f"<bases>\n{bases}\n</bases>\n\n"
        f"{_previous_block(prompt)}"
        f'<contexto pagina="{prompt.page}">\n{prompt.context}\n</contexto>\n\n'
        f"<trecho_grifado>\n{prompt.excerpt}\n</trecho_grifado>"
    )
    history = prompt.history or [{"role": "user", "content": "Analise o trecho grifado."}]
    contents = []
    for i, message in enumerate(history):
        text = message["content"]
        if i == 0:
            text = f"{opening}\n\n{text}"
        if i == len(history) - 1 and prompt.current is not None:
            current = json.dumps(prompt.current, ensure_ascii=False)
            text = f"<proposta_atual>\n{current}\n</proposta_atual>\n\n{text}"
        contents.append(
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": text}],
            }
        )
    return contents


async def _json_answer(system: str, contents: list[dict], schema: dict, step: str) -> dict:
    """Pede uma resposta JSON no schema dado e devolve o objeto, ou LlmApiError."""
    settings = get_settings()
    config: dict = {
        "temperature": 0,
        "maxOutputTokens": 8000,
        "responseMimeType": "application/json",
        "responseSchema": schema,
    }
    if settings.gemini_thinking_level:
        config["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
    data = await _generate(
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": config,
        }
    )
    answer, finish = _text(data)
    if finish in BLOCKED:
        raise LlmApiError("A IA não conseguiu analisar este trecho.")
    if finish != "STOP":
        logger.warning("llm_finish", extra={"step": step, "reason": finish})
    try:
        item = json.loads(answer)
        if not isinstance(item, dict):
            raise TypeError
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("llm_invalid_json", extra={"step": step})
        raise LlmApiError("A IA devolveu uma resposta inválida. Tente de novo.") from exc
    return item


async def analyze_excerpt(prompt: ExcerptPrompt) -> ExcerptAnswer:
    """Classifica o trecho grifado e propõe a regra (e a busca, se verificável)."""
    if getattr(get_settings(), "llm_mock", False) and not _configured_keys():
        from app.processing.ai import llm_mock

        return await llm_mock.analyze_excerpt(prompt)
    item = await _json_answer(EXCERPT_SYSTEM, _excerpt_contents(prompt), EXCERPT_SCHEMA, "excerpt")
    return _excerpt_answer(item)


# ---------------------------------------------------------------------------
# Regra revisada → condições de busca no CSV (botão "Gerar condições de busca")
# ---------------------------------------------------------------------------

QUERY_SYSTEM = (
    """Você é o Grifo. A pessoa grifou um trecho de um documento normativo, \
conversou com você sobre ele e revisou a regra (resumo e interpretação). Agora ela pediu \
as CONDIÇÕES DE BUSCA que encontram, nas bases CSV, os registros aos quais a regra se \
aplica (o escopo da regra), não os que a violam. Exemplo: "contratos acima de R$ 50 mil \
exigem garantia" → registros com Valor > 50000. Nada é salvo sem a aprovação dela.

A regra revisada (<regra_revisada>) é a referência principal: a pessoa pode tê-la editado \
e ela prevalece sobre a sua leitura do trecho. Use a conversa para entender os ajustes \
que ela pediu. Se houver uma busca na regra revisada, parta dela e mantenha o que não \
precisa mudar.

Devolva:
- reply: mensagem curta em português (até 4 frases) explicando quais colunas e valores \
você usou e por quê. Se as bases não permitem montar a busca, diga o que falta.
- dataset: nome exato de uma das bases, ou null se nenhuma serve.
- logic: "and" (todas as condições) ou "or" (qualquer uma).
- conditions: lista de {column, op, value, values}. column é o nome exato da coluna.

Regras das condições (as buscas nunca são SQL livre; o backend compila em SQL \
parametrizado):
- Operadores: eq, ne, gt, gte, lt, lte, between (values = [mínimo, máximo]), in e \
not_in (values = lista), contains, not_contains, starts_with, ends_with (texto), \
is_null e not_null (sem valor).
- gt/gte/lt/lte/between só em colunas de número, data ou data e hora. Colunas sim/não \
aceitam só eq e ne.
- value sempre como texto: números com ponto decimal e sem milhar ("50000.00"), datas \
em AAAA-MM-DD, sim/não como "true" ou "false". Em colunas com lista de valores, use \
exatamente um dos valores listados.
- Uma regra que se aplica a todos os registros da base fica com conditions vazio.
- Use os significados, eventos e unidades já interpretados das colunas. Não trate \
assinatura, publicação, realização ou vencimento como datas equivalentes. Não invente \
colunas nem valores.

"""
    + PREVIOUS_RULES_NOTE
)

QUERY_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "reply": {"type": "STRING"},
        "dataset": EXCERPT_SCHEMA["properties"]["dataset"],
        "logic": EXCERPT_SCHEMA["properties"]["logic"],
        "conditions": EXCERPT_SCHEMA["properties"]["conditions"],
    },
    "required": ["reply", "dataset", "logic", "conditions"],
    "propertyOrdering": ["reply", "dataset", "logic", "conditions"],
}


@dataclass
class QueryAnswer:
    """Busca sugerida pela IA (formato de StructuredQuery, ainda sem validar) e a explicação."""

    reply: str
    query: dict | None


def _query_contents(prompt: ExcerptPrompt) -> list[dict]:
    bases = describe_datasets(prompt.datasets) if prompt.datasets else "(nenhuma base pronta)"
    conversation = "\n".join(
        f"{'Pessoa' if m['role'] == 'user' else 'Grifo'}: {m['content']}" for m in prompt.history
    )
    current = json.dumps(prompt.current or {}, ensure_ascii=False)
    text = (
        f"<bases>\n{bases}\n</bases>\n\n"
        f"{_previous_block(prompt)}"
        f'<contexto pagina="{prompt.page}">\n{prompt.context}\n</contexto>\n\n'
        f"<trecho_grifado>\n{prompt.excerpt}\n</trecho_grifado>\n\n"
        f"<conversa>\n{conversation or '(sem conversa)'}\n</conversa>\n\n"
        f"<regra_revisada>\n{current}\n</regra_revisada>\n\n"
        "Gere as condições de busca no CSV para esta regra."
    )
    return [{"role": "user", "parts": [{"text": text}]}]


async def suggest_query(prompt: ExcerptPrompt) -> QueryAnswer:
    """Gera as condições de busca da regra revisada (nada é salvo)."""
    if getattr(get_settings(), "llm_mock", False) and not _configured_keys():
        from app.processing.ai import llm_mock

        return await llm_mock.suggest_query(prompt)
    item = await _json_answer(QUERY_SYSTEM, _query_contents(prompt), QUERY_SCHEMA, "query")
    return QueryAnswer(reply=str(item.get("reply") or "").strip(), query=query_from_answer(item))


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
    if getattr(get_settings(), "llm_mock", False) and not _configured_keys():
        yield (
            "No modo de demonstração as regras e buscas já estão prontas na tabela. "
            "A conversa com o assistente precisa de uma chave do Gemini configurada."
        )
        return
    ensure_configured()
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
            key = _select_key()
            try:
                async with (
                    _request_slot(),
                    client.stream(
                        "POST",
                        _url("streamGenerateContent"),
                        params={"alt": "sse"},
                        headers={"x-goog-api-key": key},
                        json=payload,
                    ) as response,
                ):
                    if response.status_code != 200:
                        body = (await response.aread()).decode(errors="replace")
                        if (
                            _quota_failover(key, response.status_code, body, attempt)
                            and attempt < MAX_ATTEMPTS - 1
                        ):
                            continue
                        if (
                            response.status_code not in RETRY_STATUS
                            or attempt == MAX_ATTEMPTS - 1
                            or _daily_quota(body)
                        ):
                            logger.warning("gemini_error", extra={"status": response.status_code})
                            raise LlmApiError(friendly_error(response.status_code, body))
                    else:
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
                # Release concurrency while backing off; the next attempt spends quota again.
                await asyncio.sleep(_retry_delay(attempt, body))
            except httpx.HTTPError as exc:
                raise LlmApiError(CONNECTION_ERROR) from exc
