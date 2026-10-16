"""Texto e posição das palavras de um PDF, com PyMuPDF.

O texto completo é montado palavra a palavra, então cada palavra sabe exatamente onde
começa e termina em `full_text` (offsets em code points). É isso que liga uma regra,
identificada no texto, aos retângulos que formam o grifo na página.
"""

from dataclasses import dataclass, field

import pymupdf


@dataclass
class ExtractedWord:
    page: int
    text: str
    char_start: int
    char_end: int
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class ExtractedPage:
    number: int
    width: float
    height: float
    char_start: int
    char_end: int


@dataclass
class ExtractedDocument:
    full_text: str
    pages: list[ExtractedPage] = field(default_factory=list)
    words: list[ExtractedWord] = field(default_factory=list)


class PdfReadError(Exception):
    """PDF ilegível, protegido por senha ou sem texto."""


def extract_pdf(data: bytes) -> ExtractedDocument:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfReadError(
            "Não foi possível abrir o PDF. Confira se o arquivo não está corrompido."
        ) from exc
    if doc.needs_pass:
        raise PdfReadError("Este PDF é protegido por senha.")

    parts: list[str] = []
    length = 0
    result = ExtractedDocument(full_text="")

    def append(text: str) -> int:
        nonlocal length
        start = length
        parts.append(text)
        length += len(text)
        return start

    for index, page in enumerate(doc):
        number = index + 1
        if index > 0:
            append("\n\n")
        page_start = length
        previous: tuple[int, int] | None = None
        # (x0, y0, x1, y1, texto, bloco, linha, palavra), na ordem de leitura.
        for x0, y0, x1, y1, text, block, line, _ in page.get_text("words", sort=True):
            if previous is not None:
                if block != previous[0]:
                    append("\n\n")
                elif line != previous[1]:
                    append("\n")
                else:
                    append(" ")
            start = append(text)
            result.words.append(
                ExtractedWord(number, text, start, start + len(text), x0, y0, x1, y1)
            )
            previous = (block, line)
        rect = page.rect
        result.pages.append(ExtractedPage(number, rect.width, rect.height, page_start, length))

    result.full_text = "".join(parts)
    if not result.words:
        raise PdfReadError(
            "Não encontrei texto neste PDF. Se ele for digitalizado (imagem), "
            "é preciso passar por OCR antes de enviar."
        )
    return result
