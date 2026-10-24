"""Texto puro (colado na tela ou em arquivo .txt), diagramado em PDF.

Linhas em branco separam parágrafos; quebras simples são mantidas.
"""

import re
from html import escape

from app.services.converters.base import ConvertedDocument, Converter, SourceFile
from app.services.converters.html import CleanHtml, render_clean

_PARAGRAPHS = re.compile(r"\n[ \t]*\n+")


def text_to_html(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in _PARAGRAPHS.split(text) if p.strip()]
    return "".join(
        "<p>" + "<br>".join(escape(" ".join(line.split())) for line in p.split("\n")) + "</p>"
        for p in paragraphs
    )


def title_from_text(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return (first[:80] + "…" if len(first) > 80 else first) or "Texto colado"


def decode_text(source: SourceFile) -> str:
    for encoding in filter(None, (source.charset, "utf-8-sig", "cp1252")):
        try:
            return source.data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return source.data.decode("latin-1")


class TextConverter(Converter):
    source_type = "text"
    content_types = ("text/plain",)
    extensions = (".txt",)

    def convert(self, source: SourceFile) -> ConvertedDocument:
        text = decode_text(source)
        clean = CleanHtml(title="", html=text_to_html(text), text=" ".join(text.split()))
        title = source.stem or title_from_text(text)
        return render_clean(
            clean,
            title=title[:200],
            source_type=self.source_type,
            min_chars=1,
            empty_message="O texto está vazio.",
        )
