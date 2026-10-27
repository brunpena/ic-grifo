import asyncio
import uuid
from datetime import date

import httpx
import pytest

from app.main import app
from app.services.datasets import (
    DatasetError,
    dataset_display_name,
    detect_delimiter,
    fit_to_size,
    infer_column,
    parse_csv,
    parse_value,
)

LIMITS = {"max_rows": 1000, "max_columns": 50}

CONTRATOS_BR = (
    "Número;Fornecedor;Valor;Assinatura;Ativo;CEP\n"
    "001/2026;Alfa Ltda;1.234,56;05/01/2026;sim;01310-100\n"
    "002/2026;Beta S.A.;980,00;20/02/2026;não;04538-133\n"
    "003/2026;Alfa Ltda;12.000,00;31/03/2026;sim;\n"
).encode("cp1252")


# ----- unidades -----


def test_fit_to_size_keeps_only_whole_lines_that_fit():
    data = b"a;b\n1;2\n3;4\n"
    assert fit_to_size(data, len(data)) == data
    assert fit_to_size(data, len(data) - 1) == b"a;b\n1;2\n"
    assert fit_to_size(data, 5) == b"a;b\n"
    assert fit_to_size(data, 3) == b""


def test_parse_csv_detects_schema_of_brazilian_spreadsheet():
    parsed = parse_csv(CONTRATOS_BR, **LIMITS)
    assert parsed.delimiter == ";" and parsed.encoding == "cp1252"
    types = {c.name: (c.type, c.format) for c in parsed.columns}
    assert types == {
        "Número": ("text", None),
        "Fornecedor": ("text", None),
        "Valor": ("decimal", "br"),
        "Assinatura": ("date", "br"),
        "Ativo": ("boolean", None),
        "CEP": ("text", None),
    }
    assert len(parsed.rows) == 3
    fornecedor = parsed.columns[1]
    assert fornecedor.values == ["Alfa Ltda", "Beta S.A."] and fornecedor.distinct_count == 2
    assert parsed.columns[5].null_count == 1


def test_parse_value_converts_with_column_format():
    parsed = parse_csv(CONTRATOS_BR, **LIMITS)
    valor, assinatura, ativo = (parsed.columns[i].to_dict() for i in (2, 3, 4))
    assert parse_value(valor, "12.000,00") == 12000.0
    assert parse_value(assinatura, "31/03/2026") == date(2026, 3, 31)
    assert parse_value(ativo, "não") is False
    assert parse_value(valor, None) is None
    assert parse_value(valor, "abc") is None


def test_infer_column_types():
    assert infer_column("n", ["1", "2", None]).type == "integer"
    assert (infer_column("v", ["1,234.5", "10"], "us").type, "us") == ("decimal", "us")
    # "1.500" serve nos dois padrões; o separador do arquivo decide.
    assert infer_column("v", ["1.500"], "br").type == "integer"
    assert infer_column("v", ["1.500"], "us").type == "decimal"
    assert infer_column("d", ["2026-01-05", "2026-12-31"]).format == "iso"
    assert infer_column("dt", ["2026-01-05 10:30", "2026-01-06T08:00:00"]).type == "datetime"
    assert infer_column("d", ["31/02/2026"]).type == "text"  # data impossível
    assert infer_column("cep", ["01310", "04538"]).type == "text"  # zeros à esquerda
    assert infer_column("vazia", [None, None]).type == "text"


def test_detect_delimiter():
    assert detect_delimiter("a,b,c\n1,2,3\n") == ","
    assert detect_delimiter("a;b\n1,5;2,5\n3,0;4,0\n") == ";"
    assert detect_delimiter("a\tb\n1\t2\n") == "\t"


def test_parse_csv_handles_quotes_bom_and_duplicate_headers():
    data = '﻿nome,nome,,obs\n"Silva, Ana",x,1,"linha\nquebrada"\n'.encode()
    parsed = parse_csv(data, **LIMITS)
    assert parsed.encoding == "utf-8"
    assert [c.name for c in parsed.columns] == ["nome", "nome_2", "coluna_3", "obs"]
    assert parsed.rows == [["Silva, Ana", "x", "1", "linha\nquebrada"]]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "vazio"),
        (b"a,b\n", "cabeçalho"),
        (b"a,b\n1,2,3\n", "linha 2"),
        (b"PK\x03\x04resto", "Excel"),
        (b"a,b\n" + b"1,2\n" * 1001, "limite"),
    ],
)
def test_parse_csv_rejects_invalid_files(data, message):
    with pytest.raises(DatasetError, match=message):
        parse_csv(data, **LIMITS)


def test_dataset_display_name_is_unique():
    assert dataset_display_name("contratos 2026.csv", set()) == "contratos 2026"
    assert dataset_display_name("c.csv", {"c", "c (2)"}) == "c (3)"
    assert dataset_display_name("contratos.csv.crdownload", set()) == "contratos"
    assert dataset_display_name("Unconfirmed 123.crdownload", set()) == "Unconfirmed 123"


# ----- API -----


async def _login(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Ana",
            "email": f"base-{uuid.uuid4().hex[:8]}@exemplo.com",
            "password": "senha-forte-1",
        },
    )
    assert resp.status_code == 201


async def _wait_dataset(client: httpx.AsyncClient, dataset_id: str) -> dict:
    for _ in range(100):
        body = (await client.get(f"/api/v1/datasets/{dataset_id}")).json()
        if body["status"] != "processing":
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("base não terminou de ser lida")


@pytest.mark.db
async def test_analysis_with_datasets(migrated_db, client):
    await _login(client)
    analysis = (await client.post("/api/v1/analyses", json={"title": "Contratos"})).json()
    assert analysis["datasets"] == [] and analysis["documents"] == []

    url = f"/api/v1/analyses/{analysis['id']}/datasets"
    resp = await client.post(url, files={"file": ("contratos.csv", CONTRATOS_BR, "text/csv")})
    assert resp.status_code == 202
    assert resp.json()["status"] == "processing" and resp.json()["columns"] == []
    dataset = await _wait_dataset(client, resp.json()["id"])
    assert dataset["status"] == "ready" and dataset["name"] == "contratos"
    assert dataset["row_count"] == 3 and dataset["columns"][2]["type"] == "decimal"
    # As linhas ficam só no servidor.
    assert "sample_rows" not in dataset

    again = await client.post(url, files={"file": ("contratos.csv", CONTRATOS_BR, "text/csv")})
    assert again.json()["name"] == "contratos (2)"
    await _wait_dataset(client, again.json()["id"])

    bad = await client.post(url, files={"file": ("ruim.csv", b"a,b\n1,2,3\n", "text/csv")})
    assert bad.status_code == 202
    bad = await _wait_dataset(client, bad.json()["id"])
    assert bad["status"] == "error" and "cabeçalho" in bad["status_message"]
    empty = await client.post(url, files={"file": ("vazio.csv", b" \n", "text/csv")})
    assert empty.json()["error"]["code"] == "invalid_csv"
    pdf = await client.post(url, files={"file": ("x.pdf", b"%PDF-", "application/pdf")})
    assert pdf.json()["error"]["code"] == "not_a_csv"

    listed = (await client.get("/api/v1/analyses")).json()
    assert listed[0]["id"] == analysis["id"] and listed[0]["dataset_count"] == 3

    resp = await client.delete(f"/api/v1/datasets/{dataset['id']}")
    assert resp.status_code == 204
    detail = (await client.get(f"/api/v1/analyses/{analysis['id']}")).json()
    assert [d["name"] for d in detail["datasets"]] == ["contratos (2)", "ruim"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        await _login(other)
        assert (await other.get(f"/api/v1/analyses/{analysis['id']}")).status_code == 404
        assert (await other.post(url, files={"file": ("c.csv", b"a,b\n1,2\n")})).status_code == 404

    assert (await client.delete(f"/api/v1/analyses/{analysis['id']}")).status_code == 204
    assert (await client.get(f"/api/v1/analyses/{analysis['id']}")).status_code == 404
