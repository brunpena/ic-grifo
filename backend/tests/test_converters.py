import re

import pymupdf
import pytest

from app.services.converters import (
    ConversionError,
    Converter,
    ConverterRegistry,
    SourceFile,
    UnsupportedFormatError,
    registry,
)
from app.services.converters.html import clean_html, decode_html

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Edital 12/2026</title>
<style>p { color: red }</style><script>alert("x")</script></head>
<body>
<nav><a href="/">Início</a> | <a href="/sobre">Sobre</a></nav>
<h1>Edital de seleção</h1>
<p>A contratada <b>deverá</b> entregar o relatório em até 10 dias úteis.
<p>É vedada a subcontratação.
<ul><li>Primeiro item<li>Segundo item</ul>
<table><caption>Valores</caption>
<tr><th>Item</th><th>Valor</th></tr>
<tr><td>Bolsa</td><td>R$ 700,00</td></tr>
</table>
<button>Enviar</button><noscript>ative o JavaScript</noscript>
</body></html>"""


def text_of(pdf: bytes) -> str:
    return "\n".join(page.get_text() for page in pymupdf.open(stream=pdf, filetype="pdf"))


def make_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "A contratada deverá pagar em 30 dias.")
    return doc.tobytes()


# ----- HTML -----


def test_clean_html_keeps_structure_and_drops_scripts():
    clean = clean_html(PAGE)
    assert clean.title == "Edital 12/2026"
    for kept in ("<h1>Edital de seleção</h1>", "<b>deverá</b>", "<li>Primeiro item</li>"):
        assert kept in clean.html
    for dropped in ("alert", "color: red", "Início", "Enviar", "JavaScript", "href"):
        assert dropped not in clean.html
    # Os únicos atributos são os que o próprio conversor põe nas tabelas.
    attributes = re.findall(r"<\w+ ([^>]*)>", clean.html)
    assert all(re.fullmatch(r'style="width:\d+%"|class="table-end"', a) for a in attributes)
    # Uma tabela por linha, com cabeçalho e larguras fixas.
    assert clean.html.count("<table") == 2 and "<th " in clean.html
    assert re.search(r'<td style="width:\d+%">R\$ 700,00</td>', clean.html)
    assert "<p><b>Valores</b></p>" in clean.html


def test_clean_html_escapes_text_and_survives_broken_markup():
    clean = clean_html("<head><title>t</title><body><p>1 &lt; 2 & <i>três</p></div></span>")
    assert "1 &lt; 2 &amp; <i>três</i>" in clean.html
    assert clean.text == "1 < 2 & três"


def test_decode_html_uses_meta_charset():
    data = '<meta charset="windows-1252"><p>ação</p>'.encode("cp1252")
    assert "ação" in decode_html(SourceFile(data=data))
    assert "ação" in decode_html(SourceFile(data="<p>ação</p>".encode()))


def test_html_converter_renders_text_with_word_positions():
    converted = registry.convert(SourceFile(data=PAGE.encode(), content_type="text/html"))
    assert converted.source_type == "html" and converted.title == "Edital 12/2026"
    extracted = converted.extracted
    assert "deverá entregar o relatório" in " ".join(extracted.full_text.split())
    assert "R$ 700,00" in extracted.full_text and "alert" not in extracted.full_text
    assert all(extracted.full_text[w.char_start : w.char_end] == w.text for w in extracted.words)
    assert text_of(converted.pdf).count("Bolsa") == 1


def test_long_html_table_keeps_every_row():
    rows = "".join(f"<tr><td>Linha {i}</td><td>valor {i}</td></tr>" for i in range(150))
    converted = registry.convert(
        SourceFile(data=f"<table>{rows}</table>".encode(), filename="t.html")
    )
    found = {int(n) for n in re.findall(r"Linha (\d+)", converted.extracted.full_text)}
    assert found == set(range(150)) and len(converted.extracted.pages) > 1


def test_html_without_text_is_rejected():
    page = b"<html><body><div id='app'></div><script>render()</script></body></html>"
    with pytest.raises(ConversionError, match="JavaScript"):
        registry.convert(SourceFile(data=page, content_type="text/html"))


# ----- texto e PDF -----


def test_text_converter_keeps_paragraphs():
    text = "CLÁUSULA 1\n\nA contratada deverá pagar\nem 30 dias.\n\n\nFim do texto colado."
    converted = registry.convert(SourceFile(data=text.encode(), content_type="text/plain"))
    assert converted.source_type == "text"
    assert converted.extracted.full_text.startswith("CLÁUSULA 1")
    assert "Fim do texto colado." in converted.extracted.full_text


def test_pdf_converter_and_scanned_pdf():
    converted = registry.convert(SourceFile(data=make_pdf(), filename="contrato.pdf"))
    assert converted.source_type == "pdf" and converted.title == "contrato.pdf"
    blank = pymupdf.open()
    blank.new_page()
    with pytest.raises(ConversionError, match="digitalizado"):
        registry.convert(SourceFile(data=blank.tobytes(), filename="scan.pdf"))


# ----- registro -----


def test_registry_picks_converter_by_type_extension_then_content():
    find = registry.find
    assert find(SourceFile(b"x", content_type="application/pdf")).source_type == "pdf"
    assert find(SourceFile(b"x", filename="pagina.HTM")).source_type == "html"
    octet = "application/octet-stream"
    assert find(SourceFile(make_pdf(), content_type=octet)).source_type == "pdf"
    assert find(SourceFile(b"<!DOCTYPE html><p>oi", content_type=octet)).source_type == "html"
    assert find(SourceFile(b"PK\x03\x04", filename="a.docx")) is None
    with pytest.raises(UnsupportedFormatError, match=r"\.docx"):
        registry.convert(SourceFile(b"PK\x03\x04", filename="a.docx"))


def test_new_converters_plug_into_a_registry():
    class Markdown(Converter):
        source_type = "text"
        extensions = (".md",)

        def convert(self, source):
            return registry.convert(SourceFile(source.data, content_type="text/plain"))

    custom = ConverterRegistry()
    custom.register(Markdown())
    converted = custom.convert(SourceFile("# Título\n\nA regra vale.".encode(), filename="a.md"))
    assert "A regra vale." in converted.extracted.full_text
