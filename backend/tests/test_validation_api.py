"""Fluxo real da API e banco local, com interpretação/planos da IA simulados."""

import asyncio
import uuid

import httpx
import pytest

from app.main import app
from app.schemas.validation import ValidationPlan
from app.services import llm, validation_llm
from app.services.llm import ExtractedRule

CSV = (
    b"Contrato;Assinatura;Entrega;Valor;Garantia\n"
    b"001;01/01/2026;11/01/2026;60000;5%\n"
    b"002;01/01/2026;12/01/2026;80000;2%\n"
    b"003;01/01/2026;;70000;\n"
    b"004;;12/01/2026;10000;5%\n"
)
TEXT = (
    "Entrega em até 10 dias corridos após a assinatura.\n\n"
    "Garantia de 5% para contratos acima de 50000.\n\n"
    "Manter sigilo das informações.\n\n"
    "Resposta em até 5 dias úteis."
)


@pytest.fixture
def validation_ai(monkeypatch):
    calls = []

    async def interpret(name, columns):
        return [
            {**c, "semantic": {"meaning": c["name"], "confidence": "high", "reason": "Teste"}}
            for c in columns
        ]

    async def extract(text, on_progress=None, datasets=None):
        result = []
        for marker, kind in [
            ("Entrega", "prazo"),
            ("Garantia", "condicao"),
            ("Manter", "obrigacao"),
            ("Resposta", "prazo"),
        ]:
            start = text.index(marker)
            end = text.index(".", start) + 1
            # Nenhuma associação da extração: a validação deve avaliar mesmo assim.
            result.append(ExtractedRule(kind, start, end, marker, []))
        return result

    async def plans(rules, datasets, reference_date):
        calls.append([r.summary for r in rules])
        result = {}
        for rule in rules:
            if rule.summary == "Manter":
                result[rule.ref] = ValidationPlan(
                    explanation="Não há evidência de sigilo na base",
                    missing_data=["Comprovação de sigilo"],
                )
                continue
            guarantee = rule.summary == "Garantia"
            scope = [{"column": "Valor", "op": "gt", "value": 50000}] if guarantee else []
            left = (
                {"kind": "percentage", "column": "Garantia"}
                if guarantee
                else {"kind": "days_between", "column": "Assinatura", "other_column": "Entrega"}
            )
            result[rule.ref] = ValidationPlan.model_validate(
                {
                    "explanation": "Conferência da regra",
                    "datasets": [
                        {
                            "scope": {"dataset": datasets[0].name, "conditions": scope},
                            "checks": [
                                {
                                    "left": left,
                                    "op": "gte" if guarantee else "lte",
                                    "right": {"kind": "literal", "value": 5 if guarantee else 10},
                                    "explanation": "Garantia mínima"
                                    if guarantee
                                    else "Prazo máximo",
                                }
                            ],
                        }
                    ],
                }
            )
        return result

    monkeypatch.setattr(validation_llm, "interpret_columns", interpret)
    monkeypatch.setattr(validation_llm, "plan_rules", plans)
    monkeypatch.setattr(llm, "extract_rules", extract)
    monkeypatch.setattr(llm, "ensure_configured", lambda: "test-key")
    return calls


async def ready(client, path):
    for _ in range(150):
        data = (await client.get(path)).json()
        if data["status"] in ("ready", "error"):
            assert data["status"] == "ready", data
            return data
        await asyncio.sleep(0.05)
    raise AssertionError("O processamento não terminou")


async def register(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Ana",
            "email": f"validation-{uuid.uuid4().hex[:8]}@exemplo.com",
            "password": "senha-forte-1",
        },
    )
    assert response.status_code == 201


@pytest.mark.db
async def test_general_validation_covers_all_rules_and_all_matching_rows(
    migrated_db, client, validation_ai
):
    await register(client)
    analysis = (await client.post("/api/v1/analyses", json={})).json()
    dataset = (
        await client.post(
            f"/api/v1/analyses/{analysis['id']}/datasets",
            files={"file": ("contratos.csv", CSV, "text/csv")},
        )
    ).json()
    dataset = await ready(client, f"/api/v1/datasets/{dataset['id']}")
    assert all(c["semantic"]["confidence"] == "high" for c in dataset["columns"])
    doc = (
        await client.post(
            "/api/v1/documents/text", json={"analysis_id": analysis["id"], "content": TEXT}
        )
    ).json()
    await ready(client, f"/api/v1/documents/{doc['id']}")
    url = f"/api/v1/documents/{doc['id']}/rules"
    rules = (await client.get(url)).json()
    assert validation_ai == [["Entrega", "Garantia", "Manter", "Resposta"]]
    deadline, guarantee, secrecy, business = rules
    assert all(r["query"] is None for r in rules)
    assert deadline["validation"]["status"] == guarantee["validation"]["status"] == "violacao"
    assert deadline["validation"]["passed_count"] == 1
    assert deadline["validation"]["failed_count"] == 1
    assert deadline["validation"]["unknown_count"] == 2
    assert secrecy["validation"]["status"] == business["validation"]["status"] == "inconclusiva"
    assert "feriados" in " ".join(business["validation"]["missing_data"])
    records_url = f"/api/v1/rules/{deadline['id']}/validation/records"
    records = (
        await client.get(
            records_url, params={"dataset_id": dataset["id"], "verdict": "violacao", "limit": 1}
        )
    ).json()
    assert records["total"] == 1 and records["rows"][0]["index"] == 1
    assert records["rows"][0]["verdict"] == "violacao" and records["rows"][0]["explanation"]
    page = (
        await client.get(
            records_url,
            params={
                "dataset_id": dataset["id"],
                "verdict": "inconclusiva",
                "offset": 1,
                "limit": 1,
            },
        )
    ).json()
    assert page["total"] == 2 and page["rows"][0]["index"] == 3
    # Revisão humana não sobrescreve o resultado nos dados.
    updated = (
        await client.patch(f"/api/v1/rules/{deadline['id']}", json={"status": "validada"})
    ).json()
    assert updated["validation"]["status"] == "violacao"
    # A regra rejeitada continua no relatório, explicitamente desconsiderada.
    await client.patch(f"/api/v1/rules/{secrecy['id']}", json={"status": "rejeitada"})
    response = await client.post(f"/api/v1/documents/{doc['id']}/validation")
    assert response.status_code == 202
    await ready(client, f"/api/v1/documents/{doc['id']}")
    rules = (await client.get(url)).json()
    assert rules[2]["validation"]["status"] == "ignorada"
    # O acesso às evidências respeita o dono do documento.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as other:
        await register(other)
        assert (
            await other.get(records_url, params={"dataset_id": dataset["id"]})
        ).status_code == 404
        assert (await other.post(f"/api/v1/documents/{doc['id']}/validation")).status_code == 404
    # Alterações na base tornam resultados anteriores inválidos.
    await client.delete(f"/api/v1/datasets/{dataset['id']}")
    rules = (await client.get(url)).json()
    assert rules[0]["validation"] is None
    assert (await client.get(records_url, params={"dataset_id": dataset["id"]})).status_code == 409


@pytest.mark.db
async def test_rule_without_datasets_is_explicitly_inconclusive(migrated_db, client, validation_ai):
    await register(client)
    doc = (await client.post("/api/v1/documents/text", json={"content": TEXT})).json()
    await ready(client, f"/api/v1/documents/{doc['id']}")
    rules = (await client.get(f"/api/v1/documents/{doc['id']}/rules")).json()
    assert all(r["validation"]["status"] == "inconclusiva" for r in rules)
    assert validation_ai == []


@pytest.mark.db
async def test_dataset_finishing_during_validation_queues_a_fresh_complete_run(
    migrated_db, client, validation_ai, monkeypatch
):
    from app.services import ingest

    await register(client)
    analysis = (await client.post("/api/v1/analyses", json={})).json()
    url = f"/api/v1/analyses/{analysis['id']}/datasets"
    dataset = (await client.post(url, files={"file": ("base.csv", CSV, "text/csv")})).json()
    await ready(client, f"/api/v1/datasets/{dataset['id']}")
    planner = validation_llm.plan_rules
    started, release, queued = asyncio.Event(), asyncio.Event(), asyncio.Event()
    runs = 0

    async def hold_first(rules, datasets, reference_date):
        nonlocal runs
        runs += 1
        if runs == 1:
            started.set()
            await release.wait()
        return await planner(rules, datasets, reference_date)

    original_start = ingest.start_validation

    def observe(document_id, **kwargs):
        queued.set()
        original_start(document_id, **kwargs)

    monkeypatch.setattr(validation_llm, "plan_rules", hold_first)
    monkeypatch.setattr(ingest, "start_validation", observe)
    doc = (
        await client.post(
            "/api/v1/documents/text", json={"analysis_id": analysis["id"], "content": TEXT}
        )
    ).json()
    try:
        await asyncio.wait_for(started.wait(), 5)
        second = (await client.post(url, files={"file": ("outra.csv", CSV, "text/csv")})).json()
        await ready(client, f"/api/v1/datasets/{second['id']}")
        await asyncio.wait_for(queued.wait(), 5)
    finally:
        release.set()
    for _ in range(200):
        state = (await client.get(f"/api/v1/documents/{doc['id']}")).json()
        if runs >= 2 and state["status"] == "ready":
            break
        await asyncio.sleep(0.05)
    assert runs >= 2 and state["status"] == "ready"
    rules = (await client.get(f"/api/v1/documents/{doc['id']}/rules")).json()
    assert all(r["validation"]["status"] != "desatualizada" for r in rules)
    assert rules[0]["validation"]["status"] == "violacao"


@pytest.mark.db
async def test_semantic_change_during_evaluation_cannot_publish_an_old_approval(
    migrated_db, client, validation_ai, monkeypatch
):
    from app.db.models import Dataset
    from app.db.session import SessionLocal

    await register(client)
    analysis = (await client.post("/api/v1/analyses", json={})).json()
    dataset = (
        await client.post(
            f"/api/v1/analyses/{analysis['id']}/datasets",
            files={"file": ("base.csv", CSV, "text/csv")},
        )
    ).json()
    await ready(client, f"/api/v1/datasets/{dataset['id']}")
    planner = validation_llm.plan_rules

    async def change_meaning(rules, datasets, reference_date):
        async with SessionLocal() as db:
            row = await db.get(Dataset, uuid.UUID(dataset["id"]))
            row.columns = [
                {**c, "semantic": {**c["semantic"], "meaning": "Outro significado"}}
                for c in row.columns
            ]
            await db.commit()
        return await planner(rules, datasets, reference_date)

    monkeypatch.setattr(validation_llm, "plan_rules", change_meaning)
    doc = (
        await client.post(
            "/api/v1/documents/text", json={"analysis_id": analysis["id"], "content": TEXT}
        )
    ).json()
    await ready(client, f"/api/v1/documents/{doc['id']}")
    rules = (await client.get(f"/api/v1/documents/{doc['id']}/rules")).json()
    assert all(r["validation"]["status"] == "desatualizada" for r in rules)
    response = await client.get(
        f"/api/v1/rules/{rules[0]['id']}/validation/records", params={"dataset_id": dataset["id"]}
    )
    assert response.status_code == 409
