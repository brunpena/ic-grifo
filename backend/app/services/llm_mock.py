"""Respostas prontas da IA para demonstração (LLM_MOCK=true no .env).

Substitui as chamadas ao Gemini por respostas fixas, montadas para a Portaria
Normativa nº 21/2012 (Sisu) e a base `chamada_regular_sisu_2022_1.csv`:

- extração de regras: localiza trechos conhecidos da portaria no texto do PDF;
- interpretação das colunas da base;
- geração das buscas (StructuredQuery) de cada regra;
- planos de validação (escopo + critérios de cumprimento).

Todo o resto do fluxo (validação das buscas, SQL no DuckDB, paginação, grifos)
continua sendo o código real. Para outros documentos a extração devolve as regras
cujos trechos forem encontrados no texto (possivelmente nenhuma).
"""

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.schemas.validation import ValidationPlan
from app.services import llm
from app.services.query_engine import fold

MOCK_REASON = "Interpretação da IA a partir do nome, do tipo e dos exemplos da coluna."
# Coluna que identifica a base do Sisu entre as bases da análise.
SISU_MARKER = "APROVADO"


def enabled() -> bool:
    return get_settings().llm_mock


# ---------------------------------------------------------------------------
# Regras da Portaria Normativa nº 21/2012
# ---------------------------------------------------------------------------


def _col(name: str) -> dict:
    return {"kind": "column", "column": name}


def _lit(value) -> dict:
    return {"kind": "literal", "value": value}


def _check(left: dict, op: str, right: dict | None, explanation: str) -> dict:
    return {"left": left, "op": op, "right": right, "explanation": explanation}


@dataclass
class MockRule:
    type: str
    summary: str
    # Começo e fim do trecho no documento (espaços e quebras de linha são flexíveis).
    start: str
    end: str
    # Busca: condições sobre as colunas. None = nenhuma base serve para a regra.
    conditions: list[dict] | None
    reason: str
    # Plano de validação.
    plan_explanation: str
    scope: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    logic: str = "and"


APPROVED = {"column": "APROVADO", "op": "eq", "value": "S"}

RULES: list[MockRule] = [
    MockRule(
        type="obrigacao",
        summary="Selecionar estudantes exclusivamente pelos resultados do Enem",
        start="§ 1º O processo de seleção dos estudantes para as vagas disponibilizadas",
        end="do Ensino Médio - Enem.",
        conditions=[{"column": "NOTA_CANDIDATO", "op": "not_null"}],
        reason="Todos os candidatos que concorreram com nota do Enem calculada.",
        plan_explanation=(
            "Cada inscrição deve ter número de inscrição e nota final do Enem, que é a única "
            "base da seleção."
        ),
        checks=[
            _check(_col("INSCRICAO_ENEM"), "not_null", None, "Inscrição no Enem informada"),
            _check(_col("NOTA_CANDIDATO"), "not_null", None, "Nota do Enem calculada"),
        ],
    ),
    MockRule(
        type="obrigacao",
        summary="Assinar eletronicamente o Termo de Adesão ao Sisu",
        start="§ 1º O Termo de Adesão deverá ser assinado eletronicamente",
        end="de acordo com o perfil de acesso identificado e exigido.",
        conditions=None,
        reason="A base de candidatos não registra a assinatura do Termo de Adesão.",
        plan_explanation="A assinatura do Termo de Adesão não aparece nos registros da base.",
        missing=["Registro de assinatura do Termo de Adesão por instituição."],
    ),
    MockRule(
        type="obrigacao",
        summary="Informar pesos e notas mínimas por curso e turno no Termo de Adesão",
        start="IV - os pesos e as notas mínimas eventualmente estabelecidos pela instituição",
        end="em cada curso e turno;",
        conditions=[APPROVED, {"column": "MEDIA_MINIMA", "op": "not_null"}],
        reason="Aprovados em cursos que definiram média mínima para as provas do Enem.",
        plan_explanation=(
            "Nos cursos com média mínima, o candidato aprovado deve ter nota final igual ou "
            "superior à média mínima exigida."
        ),
        scope=[APPROVED, {"column": "MEDIA_MINIMA", "op": "not_null"}],
        checks=[
            _check(
                _col("NOTA_CANDIDATO"),
                "gte",
                _col("MEDIA_MINIMA"),
                "Nota do aprovado atinge a média mínima do curso",
            )
        ],
    ),
    MockRule(
        type="proibicao",
        summary="Não ofertar vagas em cursos com teste de habilidade específica",
        start="Parágrafo único. Não poderão ser oferecidas, por meio do SiSU",
        end="teste de habilidade específica.",
        conditions=None,
        reason="A base não indica quais cursos exigem teste de habilidade específica.",
        plan_explanation="Não há coluna que informe a exigência de teste de habilidade.",
        missing=["Indicação de cursos que exigem teste de habilidade específica."],
    ),
    MockRule(
        type="proibicao",
        summary="Não cobrar taxas nos processos seletivos do Sisu",
        start="I - abster-se de cobrar quaisquer tipos de taxas",
        end="âmbito do Sisu;",
        conditions=None,
        reason="A base não contém informações sobre taxas cobradas.",
        plan_explanation="Cobrança de taxas não é registrada na base de candidatos.",
        missing=["Registro de taxas cobradas pelas instituições."],
    ),
    MockRule(
        type="obrigacao",
        summary="Efetuar a matrícula dos selecionados e lançar a ocupação da vaga",
        start="VI - efetuar as matrículas ou registros acadêmicos dos estudantes selecionados",
        end="em período definido em edital divulgado pela SESu;",
        conditions=[APPROVED],
        reason="Candidatos selecionados na chamada regular, cuja matrícula deve ser lançada.",
        plan_explanation=(
            "Todo candidato aprovado deve ter a situação da matrícula lançada no sistema "
            "(diferente de pendente)."
        ),
        scope=[APPROVED],
        checks=[
            _check(
                _col("MATRICULA"),
                "ne",
                _lit("PENDENTE"),
                "Situação da matrícula lançada pela instituição",
            )
        ],
    ),
    MockRule(
        type="prazo",
        summary="Arquivar documentos de matrícula por no mínimo cinco anos",
        start="§ 1º As instituições de ensino deverão arquivar, sob sua responsabilidade",
        end="contado da data de sua apresentação.",
        conditions=None,
        reason="A base não registra o arquivamento dos documentos de matrícula.",
        plan_explanation="Arquivamento de documentos não é registrado na base.",
        missing=["Data de apresentação e de descarte dos documentos de matrícula."],
    ),
    MockRule(
        type="condicao",
        summary="Inscrever-se no Sisu apenas quem participou do Enem",
        start="Art. 13. Somente poderá se inscrever no processo seletivo do Sisu",
        end="condições estabelecidas no edital do Sisu.",
        conditions=[{"column": "INSCRICAO_ENEM", "op": "not_null"}],
        reason="Inscrições no Sisu que trazem o número de inscrição do Enem.",
        plan_explanation="Toda inscrição no Sisu deve estar vinculada a uma inscrição no Enem.",
        checks=[_check(_col("INSCRICAO_ENEM"), "not_null", None, "Inscrição no Enem informada")],
    ),
    MockRule(
        type="proibicao",
        summary="Vedar inscrição em mais de uma modalidade no mesmo curso e turno",
        start="§ 1º É vedada ao estudante a inscrição:",
        end="instituição de ensino e local de oferta;",
        conditions=[{"column": "TIPO_MOD_CONCORRENCIA", "op": "not_null"}],
        reason="Inscrições com a modalidade de concorrência escolhida pelo candidato.",
        plan_explanation=(
            "Detectar duplicidade exige agrupar as inscrições por candidato, curso e turno."
        ),
        missing=["Comparação entre inscrições do mesmo candidato (agrupamento por CPF e curso)."],
    ),
    MockRule(
        type="obrigacao",
        summary="Optar por cotas da Lei 12.711, ações afirmativas ou ampla concorrência",
        start="Art. 15. Ao se inscrever no processo seletivo do Sisu, o estudante deverá optar",
        end="III - às vagas destinadas à ampla concorrência.",
        conditions=[{"column": "MOD_CONCORRENCIA", "op": "not_null"}],
        reason="Inscrições com modalidade de concorrência informada.",
        plan_explanation=(
            "A modalidade escolhida deve ser ampla concorrência (A), Lei 12.711 (L), "
            "ação afirmativa própria (V) ou bônus (B)."
        ),
        checks=[
            _check(
                _col("TIPO_MOD_CONCORRENCIA"),
                "in",
                _lit(["A", "B", "L", "V"]),
                "Modalidade é uma das previstas no art. 15",
            )
        ],
    ),
    MockRule(
        type="obrigacao",
        summary="Classificar por nota decrescente respeitando o limite de vagas",
        start="Art. 19. Encerrado o período de inscrição, o estudante será classificado",
        end="bem como a modalidade de concorrência.",
        conditions=[APPROVED],
        reason="Candidatos aprovados, classificados dentro do limite de vagas da modalidade.",
        plan_explanation=(
            "O aprovado deve estar classificado dentro do número de vagas ofertadas na sua "
            "modalidade de concorrência."
        ),
        scope=[APPROVED],
        checks=[
            _check(
                _col("CLASSIFICACAO"),
                "lte",
                _col("QT_VAGAS_CONCORRENCIA"),
                "Classificação dentro do limite de vagas da modalidade",
            )
        ],
    ),
    MockRule(
        type="condicao",
        summary="Aplicar bônus de ações afirmativas à nota final do estudante",
        start="II - os bônus eventualmente estabelecidos pelas instituições",
        end="na forma prevista no inciso III do art. 5º desta Portaria.",
        conditions=[{"column": "PERCENTUAL_BONUS", "op": "not_null"}],
        reason="Inscrições em ofertas com percentual de bônus definido pela instituição.",
        plan_explanation="Quando há bônus, o percentual aplicado deve ser positivo.",
        scope=[{"column": "PERCENTUAL_BONUS", "op": "not_null"}],
        checks=[_check(_col("PERCENTUAL_BONUS"), "gt", _lit(0), "Percentual de bônus positivo")],
    ),
    MockRule(
        type="condicao",
        summary="Classificar cotistas da Lei 12.711 por grupos e subgrupos",
        start="Art. 20. Os estudantes que optarem por concorrer às vagas reservadas",
        end="cada um dos seguintes grupos e subgrupos de inscritos:",
        conditions=[{"column": "TIPO_MOD_CONCORRENCIA", "op": "eq", "value": "L"}],
        reason="Inscrições na modalidade de reserva de vagas da Lei nº 12.711/2012.",
        plan_explanation=(
            "Os inscritos em vagas reservadas devem estar em um subgrupo de egressos de "
            "escola pública."
        ),
        scope=[{"column": "TIPO_MOD_CONCORRENCIA", "op": "eq", "value": "L"}],
        checks=[
            _check(
                _col("MOD_CONCORRENCIA"),
                "contains",
                _lit("escola"),
                "Modalidade é de egressos de escola pública",
            )
        ],
    ),
    MockRule(
        type="condicao",
        summary="Selecionar em uma só opção, priorizando a 1ª com nota suficiente",
        start="§ 1º Nos termos do disposto no caput, o estudante será selecionado",
        end="desde que não tenha sido selecionado em sua 1ª opção.",
        conditions=[APPROVED, {"column": "OPCAO", "op": "eq", "value": 2}],
        reason="Aprovados na 2ª opção, que só pode ocorrer sem seleção na 1ª opção.",
        plan_explanation=(
            "O aprovado deve ter nota suficiente na opção em que foi selecionado (nota final "
            "maior ou igual à nota de corte)."
        ),
        scope=[APPROVED],
        checks=[
            _check(
                _col("NOTA_CANDIDATO"),
                "gte",
                _col("NOTA_CORTE"),
                "Nota do aprovado atinge a nota de corte",
            )
        ],
    ),
    MockRule(
        type="condicao",
        summary="Condicionar a matrícula à comprovação dos requisitos legais",
        start="Art. 22. A seleção do estudante assegura apenas a expectativa de direito",
        end="regulamentação em vigor.",
        conditions=[
            APPROVED,
            {
                "column": "MATRICULA",
                "op": "in",
                "value": ["EFETIVADA", "DOCUMENTACAO REJEITADA"],
            },
        ],
        reason="Aprovados cuja documentação foi analisada (matrícula efetivada ou rejeitada).",
        plan_explanation="Só pode ter matrícula efetivada quem foi selecionado na chamada.",
        scope=[{"column": "MATRICULA", "op": "eq", "value": "EFETIVADA"}],
        checks=[_check(_col("APROVADO"), "eq", _lit("S"), "Matrícula efetivada de selecionado")],
    ),
    MockRule(
        type="proibicao",
        summary="Impedir selecionado na chamada regular de entrar na lista de espera",
        start="Parágrafo único. O estudante selecionado na chamada regular",
        end="independentemente de ter realizado sua matrícula",
        conditions=[APPROVED],
        reason="Selecionados na chamada regular, que não podem participar da lista de espera.",
        plan_explanation="A base é da chamada regular e não inclui a lista de espera.",
        missing=["Base da lista de espera para cruzar com os selecionados."],
    ),
    MockRule(
        type="prazo",
        summary="Confirmar interesse na lista de espera no período do edital",
        start="Art. 24. Para constar da lista de espera, o estudante deverá confirmar",
        end="durante o período especificado no edital do processo seletivo do Sisu.",
        conditions=None,
        reason="A base não traz as manifestações de interesse na lista de espera.",
        plan_explanation="As confirmações de interesse não estão na base da chamada regular.",
        missing=["Datas das manifestações de interesse e período do edital."],
    ),
    MockRule(
        type="condicao",
        summary="Cancelar matrícula por informação falsa ou documento inidôneo",
        start="Art. 35. A prestação de informações falsas",
        end="sem prejuízo das sanções penais eventualmente cabíveis.",
        conditions=[{"column": "MATRICULA", "op": "eq", "value": "CANCELADA"}],
        reason="Matrículas canceladas, que podem decorrer de informação falsa.",
        plan_explanation="A base registra o cancelamento, mas não o motivo nem o procedimento.",
        missing=["Motivo do cancelamento e registro do contraditório e da ampla defesa."],
    ),
    MockRule(
        type="prazo",
        summary="Portaria entra em vigor na data de sua publicação",
        start="Art. 38. Esta Portaria entra em vigor",
        end="na data de sua publicação.",
        conditions=None,
        reason="A vigência da portaria não depende dos registros da base.",
        plan_explanation="Disposição sobre vigência, sem relação com os registros da base.",
        missing=["Não se aplica aos registros de candidatos."],
    ),
]


def _pattern(phrase: str) -> re.Pattern:
    return re.compile(r"\s+".join(re.escape(word) for word in phrase.split()))


def _locate(text: str, rule: MockRule) -> tuple[int, int] | None:
    start = _pattern(rule.start).search(text)
    if start is None:
        return None
    end = _pattern(rule.end).search(text, start.start())
    if end is None or end.end() - start.start() > 3000:
        return None
    return start.start(), end.end()


def _sisu_dataset(names: list[str], datasets: list[llm.DatasetPrompt]) -> str | None:
    for dataset in datasets:
        if any(c["name"] == SISU_MARKER for c in dataset.columns):
            return dataset.name
    return names[0] if names else None


async def extract_rules(
    text: str,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    datasets: list[llm.DatasetPrompt] | None = None,
) -> list[llm.ExtractedRule]:
    datasets = datasets or []
    target = _sisu_dataset([d.name for d in datasets], datasets)
    steps = 4
    for step in range(steps):
        if on_progress:
            await on_progress(step, steps)
        # Pequena pausa para a tela mostrar o progresso, como na extração real.
        await asyncio.sleep(0.8)
    if on_progress:
        await on_progress(steps, steps)
    found: list[llm.ExtractedRule] = []
    for rule in RULES:
        span = _locate(text, rule)
        if span is None:
            continue
        related = [target] if target and rule.conditions is not None else []
        found.append(llm.ExtractedRule(rule.type, span[0], span[1], rule.summary, related))
    return found


def _normalize(value: str) -> str:
    return " ".join(fold(value).split())


def _match(prompt: llm.RulePrompt) -> MockRule | None:
    summary = _normalize(prompt.summary)
    for rule in RULES:
        if _normalize(rule.summary) == summary:
            return rule
    excerpt = _normalize(prompt.excerpt)
    for rule in RULES:
        if _normalize(rule.start)[:60] in excerpt:
            return rule
    return None


async def generate_queries(
    rules: list[llm.RulePrompt], datasets: list[llm.DatasetPrompt]
) -> dict[int, llm.GeneratedQuery]:
    await asyncio.sleep(1.0)
    target = _sisu_dataset([d.name for d in datasets], datasets)
    result: dict[int, llm.GeneratedQuery] = {}
    for prompt in rules:
        rule = _match(prompt)
        if rule is None or rule.conditions is None or target is None:
            reason = rule.reason if rule else "Nenhuma coluna da base avalia esta regra."
            empty = {"dataset": "?", "logic": "and", "conditions": []}
            result[prompt.ref] = llm.GeneratedQuery(dataset=None, query=empty, reason=reason)
            continue
        result[prompt.ref] = llm.GeneratedQuery(
            dataset=target,
            query={"dataset": target, "logic": rule.logic, "conditions": rule.conditions},
            reason=rule.reason,
        )
    return result


async def plan_rules(
    rules: list[llm.RulePrompt], datasets: list[llm.DatasetPrompt], reference_date: str
) -> dict[int, ValidationPlan]:
    await asyncio.sleep(1.0)
    target = _sisu_dataset([d.name for d in datasets], datasets)
    plans: dict[int, ValidationPlan] = {}
    for prompt in rules:
        rule = _match(prompt)
        if rule is None:
            plans[prompt.ref] = ValidationPlan(
                explanation="Regra sem dados correspondentes nas bases da análise.",
                missing_data=["Dados que permitam verificar a regra."],
            )
            continue
        if not rule.checks or target is None:
            plans[prompt.ref] = ValidationPlan(
                explanation=rule.plan_explanation, missing_data=rule.missing
            )
            continue
        plans[prompt.ref] = ValidationPlan.model_validate(
            {
                "explanation": rule.plan_explanation,
                "missing_data": rule.missing,
                "datasets": [
                    {
                        "scope": {"dataset": target, "logic": "and", "conditions": rule.scope},
                        "logic": "and",
                        "checks": rule.checks,
                    }
                ],
            }
        )
    return plans


# ---------------------------------------------------------------------------
# Significado das colunas
# ---------------------------------------------------------------------------

_M = tuple[str, str, str | None, str | None]  # meaning, semantic_type, event, unit

COLUMNS: dict[str, _M] = {
    "ANO": ("Ano da edição do Sisu", "category", None, "ano"),
    "EDICAO": ("Edição do Sisu no ano (1º ou 2º semestre)", "category", None, None),
    "ETAPA": ("Código da etapa do processo seletivo", "category", None, None),
    "DS_ETAPA": ("Descrição da etapa (chamada regular)", "category", None, None),
    "CODIGO_IES": ("Código e-MEC da instituição de ensino", "identifier", None, None),
    "NOME_IES": ("Nome da instituição de ensino superior", "text", None, None),
    "SIGLA_IES": ("Sigla da instituição de ensino superior", "category", None, None),
    "UF_IES": ("UF da instituição de ensino", "category", None, None),
    "CODIGO_CAMPUS": ("Código do local de oferta (campus)", "identifier", None, None),
    "NOME_CAMPUS": ("Nome do local de oferta (campus)", "text", None, None),
    "UF_CAMPUS": ("UF do campus", "category", None, None),
    "MUNICIPIO_CAMPUS": ("Município do campus", "category", None, None),
    "CODIGO_CURSO": ("Código do curso no e-MEC", "identifier", None, None),
    "NOME_CURSO": ("Nome do curso de graduação", "text", None, None),
    "GRAU": ("Grau acadêmico do curso", "category", None, None),
    "TURNO": ("Turno do curso", "category", None, None),
    "DS_PERIODICIDADE": ("Periodicidade do curso", "category", None, None),
    "TP_COTA": ("Tipo de cota da reserva de vagas", "category", None, None),
    "TIPO_MOD_CONCORRENCIA": (
        "Tipo da modalidade de concorrência: A ampla, L Lei 12.711, V ação afirmativa, B bônus",
        "category",
        None,
        None,
    ),
    "MOD_CONCORRENCIA": ("Descrição da modalidade de concorrência", "category", None, None),
    "QT_VAGAS_CONCORRENCIA": (
        "Quantidade de vagas ofertadas na modalidade",
        "amount",
        None,
        "vagas",
    ),
    "PERCENTUAL_BONUS": ("Percentual de bônus sobre a nota do Enem", "amount", None, "%"),
    "PESO_L": ("Peso da prova de Linguagens", "amount", None, "peso"),
    "PESO_CH": ("Peso da prova de Ciências Humanas", "amount", None, "peso"),
    "PESO_CN": ("Peso da prova de Ciências da Natureza", "amount", None, "peso"),
    "PESO_M": ("Peso da prova de Matemática", "amount", None, "peso"),
    "PESO_R": ("Peso da Redação", "amount", None, "peso"),
    "NOTA_MINIMA_L": ("Nota mínima exigida em Linguagens", "amount", None, "pontos"),
    "NOTA_MINIMA_CH": ("Nota mínima exigida em Ciências Humanas", "amount", None, "pontos"),
    "NOTA_MINIMA_CN": (
        "Nota mínima exigida em Ciências da Natureza",
        "amount",
        None,
        "pontos",
    ),
    "NOTA_MINIMA_M": ("Nota mínima exigida em Matemática", "amount", None, "pontos"),
    "NOTA_MINIMA_R": ("Nota mínima exigida na Redação", "amount", None, "pontos"),
    "MEDIA_MINIMA": ("Média mínima exigida pelo curso", "amount", None, "pontos"),
    "CPF": ("CPF mascarado do candidato", "identifier", None, None),
    "INSCRICAO_ENEM": ("Número de inscrição do candidato no Enem", "identifier", None, None),
    "INSCRITO": ("Nome do candidato inscrito", "text", None, None),
    "SEXO": ("Sexo do candidato", "category", None, None),
    "DATA_NASCIMENTO": ("Data de nascimento do candidato", "date", "nascimento", None),
    "UF_CANDIDATO": ("UF de residência do candidato", "category", None, None),
    "MUNICIPIO_CANDIDATO": ("Município de residência do candidato", "category", None, None),
    "OPCAO": ("Opção de curso do candidato (1ª ou 2ª)", "category", None, None),
    "NOTA_L": ("Nota em Linguagens no Enem", "amount", None, "pontos"),
    "NOTA_CH": ("Nota em Ciências Humanas no Enem", "amount", None, "pontos"),
    "NOTA_CN": ("Nota em Ciências da Natureza no Enem", "amount", None, "pontos"),
    "NOTA_M": ("Nota em Matemática no Enem", "amount", None, "pontos"),
    "NOTA_R": ("Nota da Redação no Enem", "amount", None, "pontos"),
    "NOTA_L_COM_PESO": ("Nota de Linguagens multiplicada pelo peso", "amount", None, "pontos"),
    "NOTA_CH_COM_PESO": (
        "Nota de Ciências Humanas multiplicada pelo peso",
        "amount",
        None,
        "pontos",
    ),
    "NOTA_CN_COM_PESO": (
        "Nota de Ciências da Natureza multiplicada pelo peso",
        "amount",
        None,
        "pontos",
    ),
    "NOTA_M_COM_PESO": ("Nota de Matemática multiplicada pelo peso", "amount", None, "pontos"),
    "NOTA_R_COM_PESO": ("Nota da Redação multiplicada pelo peso", "amount", None, "pontos"),
    "NOTA_CANDIDATO": (
        "Nota final do candidato (média ponderada com bônus)",
        "amount",
        None,
        "pontos",
    ),
    "NOTA_CORTE": ("Nota de corte da opção e modalidade", "amount", None, "pontos"),
    "CLASSIFICACAO": (
        "Posição do candidato na classificação da modalidade",
        "amount",
        None,
        "posição",
    ),
    "APROVADO": ("Indica se o candidato foi selecionado (S/N)", "boolean", "seleção", None),
    "MATRICULA": ("Situação da matrícula do candidato", "status", "matrícula", None),
}


def _meaning(column: dict) -> dict:
    known = COLUMNS.get(column["name"])
    if known is None:
        return {
            "meaning": f"Coluna “{column['name']}” da base",
            "semantic_type": "text" if column.get("type") == "text" else "unknown",
            "event": None,
            "unit": None,
            "confidence": "high",
            "reason": MOCK_REASON,
        }
    meaning, semantic_type, event, unit = known
    return {
        "meaning": meaning,
        "semantic_type": semantic_type,
        "event": event,
        "unit": unit,
        "confidence": "high",
        "reason": MOCK_REASON,
    }


def needs_meanings(columns: list[dict]) -> bool:
    """Colunas interpretadas antes (pela IA real ou sem sucesso) são refeitas pelo mock."""
    return any((c.get("semantic") or {}).get("reason") != MOCK_REASON for c in columns)


async def interpret_columns(name: str, columns: list[dict]) -> list[dict]:
    await asyncio.sleep(0.5)
    return [{**c, "semantic": _meaning(c)} for c in columns]
