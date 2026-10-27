"""Conferência independente da IA: prazos, dados ausentes, escopo e evidências."""

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.schemas.validation import (
    ComplianceCheck,
    DatasetCheck,
    DatasetValidation,
    ValidationPlan,
)
from app.services import compliance, validation_llm
from app.services.datasets import parse_csv, parse_value
from app.services.query_engine import DatasetRef, QueryError

CSV = (
    b"Contrato;Assinatura;Entrega;Valor;Garantia\n"
    b"001;01/01/2026;11/01/2026;60000;5%\n"
    b"002;01/01/2026;12/01/2026;80000;2%\n"
    b"003;01/01/2026;;70000;\n"
    b"004;;12/01/2026;10000;5%\n"
)
TODAY = date(2026, 10, 27)


def data():
    parsed = parse_csv(CSV)
    columns = [
        {**c.to_dict(), "semantic": {"meaning": c.name, "confidence": "high"}}
        for c in parsed.columns
    ]
    rows = [[parse_value(c, row[i]) for i, c in enumerate(columns)] for row in parsed.rows]
    return DatasetRef(id=uuid.uuid4(), name="contratos", columns=columns), parsed.rows, rows


def check(kind="days_between", column="Assinatura", other="Entrega", op="lte", value=10):
    left = {"kind": kind, "column": column}
    if other:
        left["other_column"] = other
    return {
        "left": left,
        "op": op,
        "right": {"kind": "literal", "value": value},
        "explanation": "Critério da regra",
    }


def compiled(ref, checks=None, scope=None, missing=None, logic="and"):
    plan = DatasetCheck.model_validate(
        {
            "scope": {"dataset": ref.name, "conditions": scope or []},
            "logic": logic,
            "checks": checks or [check()],
        }
    )
    return compliance.compile_validation(plan, ref, TODAY, missing or [])


def test_deadline_checks_every_record_and_keeps_missing_dates_inconclusive():
    ref, raw, rows = data()
    counts, total, evidence = compliance.evaluate_rows(compiled(ref), raw, rows)
    assert counts == {
        "applicable_count": 4,
        "passed_count": 1,
        "failed_count": 1,
        "unknown_count": 2,
    }
    assert total == 4
    assert [r.verdict for r in evidence] == ["conforme", "violacao", "inconclusiva", "inconclusiva"]
    assert "11.0" in evidence[1].explanation


def test_guarantee_uses_scope_and_percentage_not_just_presence():
    ref, raw, rows = data()
    c = compiled(
        ref,
        [check("percentage", "Garantia", None, "gte", 5)],
        [{"column": "Valor", "op": "gt", "value": 50000}],
    )
    counts, total, evidence = compliance.evaluate_rows(c, raw, rows, verdict="violacao", limit=1)
    assert counts["passed_count"] == counts["failed_count"] == counts["unknown_count"] == 1
    assert total == 1 and evidence[0].index == 1


def test_empty_or_inverted_dates_do_not_prove_compliance():
    ref, _, rows = data()
    c = compiled(ref)
    rows[0][1], rows[0][2] = date(2026, 2, 1), date(2026, 1, 1)
    assert c.evaluate(rows[0])[0] == "inconclusiva"


def test_missing_scope_value_is_inconclusive_not_silently_excluded():
    ref, raw, rows = data()
    c = compiled(ref, scope=[{"column": "Assinatura", "op": "gt", "value": "2025-01-01"}])
    assert c.evaluate(rows[3])[0] == "inconclusiva"
    counts, total, _ = compliance.evaluate_rows(c, raw, rows)
    assert counts["applicable_count"] == total == 4


def test_uncertain_semantics_cannot_approve_or_exclude_records():
    ref, _, rows = data()
    ref.columns[3]["semantic"]["confidence"] = "low"
    c = compiled(ref, scope=[{"column": "Valor", "op": "gt", "value": 50000}])
    assert c.evaluate(rows[3])[0] == "inconclusiva"
    assert "não confirmado" in c.evaluate(rows[3])[1]


def test_incomplete_rule_evidence_is_inconclusive_even_when_supported_part_passes():
    ref, _, rows = data()
    assert (
        compiled(ref, missing=["Comprovação de recebimento"]).evaluate(rows[0])[0] == "inconclusiva"
    )


@pytest.mark.parametrize(
    "logic,values,expected",
    [
        ("and", [True, None], None),
        ("and", [False, None], False),
        ("or", [True, None], True),
        ("or", [False, None], None),
    ],
)
def test_three_valued_logic(logic, values, expected):
    assert compliance.combine(values, logic) is expected


@pytest.mark.parametrize(
    "start,quantity,unit,expected",
    [
        (date(2024, 1, 31), 1, "months", date(2024, 2, 29)),
        (date(2024, 2, 29), 1, "years", date(2025, 2, 28)),
        (date(2026, 1, 1), 10, "days", date(2026, 1, 11)),
    ],
)
def test_calendar_deadlines_handle_month_ends_and_leap_years(start, quantity, unit, expected):
    assert compliance._shift(start, quantity, unit) == expected


def test_deadline_compares_two_dates_and_preserves_equality_at_limit():
    ref, _, rows = data()
    test = ComplianceCheck.model_validate(
        {
            "left": {"kind": "column", "column": "Entrega"},
            "op": "lte",
            "right": {"kind": "deadline", "column": "Assinatura", "value": 10},
            "explanation": "Entrega em até 10 dias",
        }
    )
    predicate = compliance.compile_check(test, ref, TODAY)
    assert predicate(rows[0])[0] is True
    assert predicate(rows[1])[0] is False
    assert predicate(rows[2])[0] is None


def test_ratio_percent_and_zero_denominator():
    ref, _, rows = data()
    ref.columns.append(
        {"name": "GarantiaValor", "type": "decimal", "semantic": {"confidence": "high"}}
    )
    for row in rows:
        row.append(3000)
    test = ComplianceCheck.model_validate(check("ratio_percent", "GarantiaValor", "Valor", "eq", 5))
    predicate = compliance.compile_check(test, ref, TODAY)
    assert predicate(rows[0])[0] is True
    rows[0][3] = 0
    assert predicate(rows[0])[0] is None


def test_invalid_percentage_and_nonfinite_values_are_inconclusive():
    ref, _, rows = data()
    rows[0][4] = "não informado"
    c = compiled(ref, [check("percentage", "Garantia", None, "gte", 5)])
    assert c.evaluate(rows[0])[0] == "inconclusiva"
    rows[0][3] = float("inf")
    c = compiled(ref, [check("column", "Valor", None, "gt", 1)])
    assert c.evaluate(rows[0])[0] == "inconclusiva"


def test_pagination_filters_full_results_before_paging():
    ref, raw, rows = data()
    _, total, page = compliance.evaluate_rows(
        compiled(ref), raw, rows, offset=1, limit=1, verdict="inconclusiva"
    )
    assert total == 2 and page[0].index == 3


@pytest.mark.parametrize(
    "bad",
    [
        check("column", "Inexistente", None),
        check("column", "Contrato", None, "gt", 1),
        check("days_between", "Valor", "Entrega"),
        check("column", "Valor", None, "between", [1]),
    ],
)
def test_invalid_columns_types_and_operators_are_rejected(bad):
    ref, _, _ = data()
    with pytest.raises(QueryError):
        compiled(ref, [bad])


def test_tautological_plan_without_a_data_column_is_rejected():
    ref, _, _ = data()
    bad = {
        "left": {"kind": "today"},
        "op": "eq",
        "right": {"kind": "literal", "value": TODAY.isoformat()},
        "explanation": "Sem evidência",
    }
    with pytest.raises(QueryError, match="coluna"):
        compiled(ref, [bad])


def test_free_code_is_not_an_operand():
    with pytest.raises(ValidationError):
        ComplianceCheck.model_validate(
            {"left": {"kind": "eval", "value": "1+1"}, "op": "eq", "explanation": "Não permitido"}
        )


def test_zero_matches_and_missing_datasets_are_not_compliance():
    plan = ValidationPlan(explanation="Critério da regra")
    now = datetime.now(UTC)
    assert compliance.summarize(plan, [], now, []).status == "inconclusiva"
    ds = DatasetValidation(dataset_id=uuid.uuid4(), dataset_name="contratos")
    assert compliance.summarize(plan, [ds], now, []).status == "nao_aplicavel"
    ds.failed_count = 1
    ds.applicable_count = 1
    assert compliance.summarize(plan, [ds], now, []).status == "violacao"


async def test_ai_column_interpretation_keeps_physical_types_and_marks_missing_columns(monkeypatch):
    ref, _, _ = data()

    async def fake(system, payload):
        assert len(payload["columns"]) == len(ref.columns)
        return {
            "columns": [
                {
                    "name": "Assinatura",
                    "meaning": "Data de assinatura do contrato",
                    "semantic_type": "date",
                    "confidence": "high",
                    "event": "assinatura",
                }
            ]
        }

    monkeypatch.setattr(validation_llm, "_json", fake)
    monkeypatch.setattr(validation_llm.llm, "ensure_configured", lambda: "test")
    columns = await validation_llm.interpret_columns(ref.name, ref.columns)
    assert columns[1]["semantic"]["event"] == "assinatura" and columns[1]["type"] == "date"
    assert columns[0]["semantic"]["confidence"] == "low"


async def test_ai_plan_batch_failure_is_not_a_silent_approval(monkeypatch):
    from app.services.llm import RulePrompt

    async def fake(system, payload):
        return {
            "plans": [{"ref": 1, "explanation": "Verificar prazo", "datasets": [{"bad": "schema"}]}]
        }

    monkeypatch.setattr(validation_llm, "_json", fake)
    monkeypatch.setattr(validation_llm.llm, "ensure_configured", lambda: "test")
    result = await validation_llm.plan_rules(
        [RulePrompt(1, "prazo", "Prazo", "Em 10 dias")], [], "2026-01-01"
    )
    assert result == {}


def test_source_signature_changes_when_column_meaning_changes():
    from types import SimpleNamespace

    from app.services.rule_validation import source_signature

    ref, _, _ = data()
    source = SimpleNamespace(
        status="ready", size_bytes=100, original_size_bytes=100, columns=ref.columns
    )
    previous = source_signature(source)
    source.columns[1]["semantic"]["meaning"] = "Outro evento"
    assert source_signature(source) != previous


def test_measured_business_days_can_be_checked_without_calendar_arithmetic():
    from types import SimpleNamespace

    from app.services.rule_validation import measured_business_days

    plan = ValidationPlan.model_validate(
        {
            "explanation": "Prazo em dias úteis",
            "datasets": [
                {
                    "scope": {"dataset": "base"},
                    "checks": [check("column", "Duração", None, "lte", 5)],
                }
            ],
        }
    )
    dataset = SimpleNamespace(
        name="base",
        columns=[
            {
                "name": "Duração",
                "type": "integer",
                "semantic": {"confidence": "high", "unit": "dias úteis"},
            }
        ],
    )
    assert measured_business_days(plan, [dataset])
    dataset.columns[0]["semantic"]["unit"] = "dias corridos"
    assert not measured_business_days(plan, [dataset])


def test_deadline_date_cannot_precede_its_start():
    ref, _, rows = data()
    test = ComplianceCheck.model_validate(
        {
            "left": {"kind": "column", "column": "Entrega"},
            "op": "lte",
            "right": {"kind": "deadline", "column": "Assinatura", "value": 10},
            "explanation": "Prazo",
        }
    )
    rows[0][2] = date(2025, 12, 31)
    assert compliance.compile_check(test, ref, TODAY)(rows[0])[0] is None
