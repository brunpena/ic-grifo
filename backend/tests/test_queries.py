import asyncio
import uuid

import pytest

from app.schemas.queries import StructuredQuery
from app.services import llm
from app.services.datasets import parse_csv, parse_value
from app.services.llm import ExtractedRule, GeneratedQuery
from app.services.query_engine import DatasetRef, QueryError, compile_query, run

CSV = (
    "Número;Fornecedor;Valor;Assinatura;Ativo;Modalidade;Garantia\n"
    "001;Alfa Ltda;1.234,56;05/01/2026;sim;Pregão;\n"
    "002;Beta S.A.;80.000,00;20/02/2026;não;Dispensa;5%\n"
    "003;Ação Serviços;17.600,50;31/03/2026;sim;Inexigibilidade;\n"
    "004;alfa ltda;55.000,00;15/04/2026;sim;Pregão;5%\n"
).encode()


@pytest.fixture(scope="module")
def dataset():
    parsed = parse_csv(CSV, max_rows=100, max_columns=20)
    columns = [c.to_dict() for c in parsed.columns]
    rows = [[parse_value(c, row[i]) for i, c in enumerate(columns)] for row in parsed.rows]
    return DatasetRef(id=uuid.uuid4(), name="contratos", columns=columns), rows


def matches(dataset, conditions, logic="and"):
    ref, rows = dataset
    query = StructuredQuery.model_validate(
        {"dataset": "contratos", "logic": logic, "conditions": conditions}
    )
    compiled = compile_query(query, [ref])
    return [rows[i][0] for i in run(compiled, rows)], compiled.normalized


def test_numeric_and_date_comparisons(dataset):
    assert matches(dataset, [{"column": "Valor", "op": "gt", "value": 50000}])[0] == ["002", "004"]
    # Número canônico numa coluna em formato brasileiro.
    found, normalized = matches(dataset, [{"column": "Valor", "op": "gte", "value": "17600.50"}])
    assert found == ["002", "003", "004"]
    assert normalized.conditions[0].value == 17600.5
    found, normalized = matches(
        dataset,
        [{"column": "assinatura", "op": "between", "value": ["31/03/2026", "2026-02-01"]}],
    )
    assert found == ["002", "003"]
    # Nome da coluna corrigido e datas guardadas em ISO, já na ordem.
    assert normalized.conditions[0].column == "Assinatura"
    assert normalized.conditions[0].value == ["2026-02-01", "2026-03-31"]


def test_text_ignores_case_and_accents(dataset):
    assert matches(dataset, [{"column": "Fornecedor", "op": "eq", "value": "ALFA LTDA"}])[0] == [
        "001",
        "004",
    ]
    assert matches(dataset, [{"column": "Fornecedor", "op": "contains", "value": "acao"}])[0] == [
        "003"
    ]
    found, _ = matches(
        dataset, [{"column": "Modalidade", "op": "in", "value": ["Dispensa", "inexigibilidade"]}]
    )
    assert found == ["002", "003"]


def test_nulls_booleans_and_groups(dataset):
    assert matches(dataset, [{"column": "Garantia", "op": "is_null"}])[0] == ["001", "003"]
    # Célula vazia não entra em "diferente de".
    assert matches(dataset, [{"column": "Garantia", "op": "ne", "value": "10%"}])[0] == [
        "002",
        "004",
    ]
    assert matches(dataset, [{"column": "Ativo", "op": "eq", "value": "false"}])[0] == ["002"]
    found, _ = matches(
        dataset,
        [
            {"column": "Valor", "op": "gt", "value": 17000},
            {
                "logic": "or",
                "conditions": [
                    {"column": "Modalidade", "op": "eq", "value": "Dispensa"},
                    {"column": "Modalidade", "op": "eq", "value": "Inexigibilidade"},
                ],
            },
        ],
    )
    assert found == ["002", "003"]
    assert len(matches(dataset, [])[0]) == 4  # sem condições: todos os registros


@pytest.mark.parametrize(
    ("conditions", "message"),
    [
        ([{"column": "Prazo", "op": "eq", "value": 1}], "não existe"),
        ([{"column": "Fornecedor", "op": "gt", "value": "a"}], "não serve"),
        ([{"column": "Ativo", "op": "lt", "value": "true"}], "não serve"),
        ([{"column": "Valor", "op": "gt", "value": "muito"}], "número"),
        ([{"column": "Assinatura", "op": "eq", "value": "ontem"}], "data"),
        ([{"column": "Valor", "op": "between", "value": [1]}], "dois valores"),
        ([{"column": "Valor", "op": "in", "value": 3}], "lista"),
        ([{"column": "Valor", "op": "eq"}], "Informe um valor"),
        ([{"column": "Valor", "op": "gt", "value": 1}] * 31, "no máximo 30"),
    ],
)
def test_invalid_queries_have_clear_messages(dataset, conditions, message):
    with pytest.raises(QueryError, match=message):
        matches(dataset, conditions)


def test_unknown_dataset_and_deep_groups(dataset):
    ref, _ = dataset
    with pytest.raises(QueryError, match="não existe nesta análise"):
        compile_query(StructuredQuery(dataset="outra"), [ref])
    deep = {"logic": "and", "conditions": [{"column": "Valor", "op": "gt", "value": 1}]}
    for _ in range(3):
        deep = {"logic": "and", "conditions": [deep]}
    with pytest.raises(QueryError, match="níveis"):
        compile_query(StructuredQuery.model_validate({"dataset": "contratos", **deep}), [ref])


def test_ai_answer_is_sanitized_before_validation():
    answer = llm._query_from_answer(
        {
            "dataset": "contratos",
            "logic": "talvez",
            "conditions": [
                {"column": "Valor", "op": "gt", "value": 5},
                {"column": "Modalidade", "op": "in", "values": ["A", "B"]},
                {"column": "Garantia", "op": "is_null", "value": "x"},
                {"column": "", "op": "eq", "value": "sem coluna"},
                {"column": "Valor", "op": "DROP TABLE", "value": "1"},
            ],
        }
    )
    query = StructuredQuery.model_validate(answer.query)
    assert query.logic == "and"
    assert [(c.op, c.value) for c in query.conditions] == [
        ("gt", "5"),
        ("in", ["A", "B"]),
        ("is_null", None),
    ]


def test_dataset_context_for_the_prompt(dataset):
    ref, _ = dataset
    text = llm.describe_datasets([llm.DatasetPrompt(ref.name, 4, ref.columns)])
    assert '<base nome="contratos" linhas="4">' in text
    assert "- Valor (decimal) ex.: 1.234,56" in text
    assert "- Modalidade (texto) valores: Dispensa | Inexigibilidade | Pregão" in text
    schema = llm._extraction_schema(["contratos"])
    item = schema["properties"]["rules"]["items"]
    assert item["properties"]["datasets"]["items"]["enum"] == ["contratos"]
    assert llm._extraction_schema([]) is llm.EXTRACTION_SCHEMA


# ----- fluxo completo, com a IA simulada -----


TEXT = (
    "CLÁUSULA 1\n\n"
    "Contratos acima de R$ 50.000,00 exigem garantia de 5% do valor.\n\n"
    "A contratada deverá manter sigilo sobre as informações."
)


@pytest.fixture
def fake_ai(monkeypatch):
    calls = []

    async def extract(text, on_progress=None, datasets=None):
        names = [d.name for d in datasets or []]
        start = text.index("Contratos acima")
        end = text.index("valor.") + len("valor.")
        other = text.index("A contratada")
        return [
            ExtractedRule("condicao", start, end, "Garantia acima de 50 mil", names[:1]),
            ExtractedRule("obrigacao", other, len(text), "Manter sigilo", []),
        ]

    async def generate(rules, datasets):
        calls.append([r.summary for r in rules])
        result = {}
        for r in rules:
            if "Garantia" in r.summary:
                result[r.ref] = GeneratedQuery(
                    "contratos",
                    {
                        "dataset": "contratos",
                        "logic": "and",
                        "conditions": [{"column": "Valor", "op": "gt", "value": "50000"}],
                    },
                    "Contratos acima de 50 mil",
                )
            else:
                result[r.ref] = GeneratedQuery(None, {}, "Nenhuma base tem sigilo")
        return result

    monkeypatch.setattr(llm, "extract_rules", extract)
    monkeypatch.setattr(llm, "generate_queries", generate)
    monkeypatch.setattr(llm, "ensure_configured", lambda: "chave")
    return calls


async def _login(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Ana",
            "email": f"busca-{uuid.uuid4().hex[:8]}@exemplo.com",
            "password": "senha-forte-1",
        },
    )
    assert resp.status_code == 201


async def _wait_ready(client, doc_id):
    for _ in range(100):
        body = (await client.get(f"/api/v1/documents/{doc_id}")).json()
        if body["status"] in ("ready", "error"):
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("documento não terminou de processar")


@pytest.mark.db
async def test_rules_become_queries_over_the_datasets(migrated_db, client, fake_ai):
    await _login(client)
    analysis = (await client.post("/api/v1/analyses", json={})).json()
    dataset = (
        await client.post(
            f"/api/v1/analyses/{analysis['id']}/datasets",
            files={"file": ("contratos.csv", CSV, "text/csv")},
        )
    ).json()
    doc = (
        await client.post(
            "/api/v1/documents/text", json={"analysis_id": analysis["id"], "content": TEXT}
        )
    ).json()
    assert (await _wait_ready(client, doc["id"]))["status"] == "ready"
    # Só a regra ligada a uma base foi para a IA gerar a busca.
    assert fake_ai == [["Garantia acima de 50 mil"]]

    garantia, sigilo = (await client.get(f"/api/v1/documents/{doc['id']}/rules")).json()
    assert garantia["dataset_ids"] == [dataset["id"]] and sigilo["query"] is None
    query = garantia["query"]
    assert query["state"] == "ok" and query["origin"] == "ia" and query["match_count"] == 2
    assert query["dataset_name"] == "contratos" and query["verdict"] is None
    assert query["query"]["conditions"][0]["value"] == 50000

    records = (await client.get(f"/api/v1/rules/{garantia['id']}/records?limit=1")).json()
    assert records["total"] == 2 and records["columns"][0] == "Número"
    assert [r["index"] for r in records["rows"]] == [1] and records["rows"][0]["values"][0] == "002"

    # Correção manual: uma busca inválida volta 422 e não muda nada.
    url = f"/api/v1/rules/{garantia['id']}/query"
    bad = await client.put(
        url, json={"dataset": "contratos", "conditions": [{"column": "X", "op": "eq", "value": 1}]}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_query"
    resp = await client.put(
        url,
        json={
            "dataset": "contratos",
            "conditions": [
                {"column": "Valor", "op": "gt", "value": 50000},
                {"column": "Garantia", "op": "is_null"},
            ],
        },
    )
    assert resp.status_code == 200
    manual = resp.json()["query"]
    assert manual["origin"] == "manual" and manual["match_count"] == 0

    # Regerar com a IA, mesmo sobrescrevendo, não mexe na busca manual.
    resp = await client.post(f"/api/v1/documents/{doc['id']}/queries", json={"overwrite": True})
    assert resp.status_code == 202
    await _wait_ready(client, doc["id"])
    assert fake_ai[-1] == ["Manter sigilo"]
    garantia = (await client.get(f"/api/v1/documents/{doc['id']}/rules")).json()[0]
    assert garantia["query"]["origin"] == "manual"

    # Sem a base, a busca fica com erro e os registros deixam de ser servidos.
    await client.delete(f"/api/v1/datasets/{dataset['id']}")
    garantia = (await client.get(f"/api/v1/documents/{doc['id']}/rules")).json()[0]
    assert garantia["query"]["state"] == "erro" and "removida" in garantia["query"]["error"]
    assert (await client.get(f"/api/v1/rules/{garantia['id']}/records")).status_code == 409
    resp = await client.post(f"/api/v1/documents/{doc['id']}/queries", json={})
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "no_datasets"

    assert (await client.delete(url)).status_code == 204
    garantia = (await client.get(f"/api/v1/documents/{doc['id']}/rules")).json()[0]
    assert garantia["query"] is None
