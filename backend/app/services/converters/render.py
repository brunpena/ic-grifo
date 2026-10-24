"""Diagramação de HTML limpo em PDF (A4), com o `Story` do PyMuPDF.

O HTML chega já sanitizado (ver `converters.html`). O MuPDF perde linhas quando uma
tabela atravessa a quebra de página, por isso cada linha de tabela vira uma tabela
própria, com as mesmas larguras de coluna (ver `html.HtmlCleaner`).
"""

import io

import pymupdf

from app.services.converters.base import ConversionError

PAGE = pymupdf.paper_rect("a4")
MARGIN = 56  # ~2 cm
CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.35; color: #111; }
h1 { font-size: 18pt; margin: 0 0 8pt 0; }
h2 { font-size: 15pt; margin: 12pt 0 6pt 0; }
h3 { font-size: 13pt; margin: 10pt 0 4pt 0; }
h4, h5, h6 { font-size: 11pt; margin: 8pt 0 4pt 0; }
p { margin: 0 0 6pt 0; }
ul, ol { margin: 0 0 6pt 0; }
li { margin: 0 0 2pt 0; }
pre { font-family: monospace; font-size: 9.5pt; margin: 0 0 6pt 0; }
blockquote { margin: 0 0 6pt 16pt; }
table { width: 100%; border-collapse: collapse; margin: 0; }
td, th { border: 0.5pt solid #999; padding: 2pt 4pt; vertical-align: top; text-align: left; }
th { font-weight: bold; background-color: #eef2f8; }
.table-end { margin: 0 0 8pt 0; }
"""


def html_to_pdf(html: str) -> bytes:
    try:
        story = pymupdf.Story(html=html, user_css=CSS)
        buffer = io.BytesIO()
        writer = pymupdf.DocumentWriter(buffer)
        where = PAGE + (MARGIN, MARGIN, -MARGIN, -MARGIN)
        more = True
        while more:
            device = writer.begin_page(PAGE)
            more, _ = story.place(where)
            story.draw(device)
            writer.end_page()
        writer.close()
    except Exception as exc:
        raise ConversionError("Não foi possível diagramar o conteúdo em páginas.") from exc
    return buffer.getvalue()
