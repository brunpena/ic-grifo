"""Páginas HTML: texto com a estrutura (títulos, parágrafos, listas e tabelas), sem
scripts, estilos e elementos interativos. O resultado é diagramado em PDF.

Usa só o `html.parser` da biblioteca padrão. O HTML de saída nunca carrega atributos,
links ou recursos externos: só as tags de `KEEP`, com o texto escapado.
"""

import codecs
import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser

from app.services.converters.base import ConversionError, ConvertedDocument, Converter, SourceFile
from app.services.converters.render import html_to_pdf
from app.services.pdf_text import PdfReadError, extract_pdf

# Descartadas com tudo o que têm dentro.
DROP = {
    "script", "style", "noscript", "template", "svg", "math", "canvas", "iframe", "object",
    "embed", "nav", "button", "select", "option", "textarea", "audio", "video", "head",
    "dialog", "map",
}  # fmt: skip
VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
    "source", "track", "wbr",
}  # fmt: skip
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
INLINE_KEEP = {"b", "strong", "i", "em", "u", "sub", "sup", "code"}
# Saem como estão (sem atributos); o resto é desembrulhado (fica só o conteúdo).
KEEP = HEADINGS | INLINE_KEEP | {"p", "ul", "ol", "li", "pre", "blockquote", "br"}
# Contêineres de bloco: viram <div>, para o texto de dentro não grudar no vizinho.
BLOCKS = {
    "div", "section", "article", "main", "header", "footer", "aside", "figure", "figcaption",
    "address", "dl", "dt", "dd", "center", "form", "fieldset", "details", "summary", "legend",
    "hr", "body",
}  # fmt: skip
# Abrir uma destas fecha a tag do mesmo grupo que estiver aberta (HTML sem </li>, </td>...).
IMPLICIT_CLOSE = {"li": {"li"}, "tr": {"tr", "td", "th"}, "td": {"td", "th"}, "th": {"td", "th"}}
CLOSES_P = BLOCKS | HEADINGS | {"p", "ul", "ol", "pre", "blockquote", "table"}

MIN_TEXT_CHARS = 20
_SPACES = re.compile(r"\s+")
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([\w-]+)""", re.IGNORECASE)


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)


class _TreeBuilder(HTMLParser):
    """Árvore tolerante a HTML mal formado (tags sem fechamento, fechamentos sobrando)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("body")
        self.stack: list[Node] = [self.root]
        self.skip = 0  # profundidade dentro de uma tag descartada
        self.in_title = False
        self.title_parts: list[str] = []

    def _close(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def _open_tags(self) -> set[str]:
        return {n.tag for n in self.stack}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self.in_title = True
            return
        if tag == "body":
            # Um <head> sem </head> não pode levar a página inteira junto.
            self.skip = 0
        if self.skip:
            if tag in DROP and tag not in VOID:
                self.skip += 1
            return
        if tag in DROP:
            if tag not in VOID:
                self.skip = 1
            return
        if tag in VOID and tag not in ("br", "hr"):
            return
        for closer in IMPLICIT_CLOSE.get(tag, ()):
            if closer in self._open_tags():
                self._close(closer)
        if tag in CLOSES_P and "p" in self._open_tags():
            self._close("p")
        node = Node(tag, {k: v or "" for k, v in attrs if k in ("colspan",)})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
            return
        if self.skip:
            if tag in DROP:
                self.skip -= 1
            return
        self._close(tag)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        elif not self.skip:
            self.stack[-1].children.append(data)


def _text(node: Node | str) -> str:
    if isinstance(node, str):
        return node
    return " ".join(_text(c) for c in node.children)


def _plain(node: Node | str) -> str:
    return _SPACES.sub(" ", _text(node)).strip()


class _Serializer:
    def __init__(self) -> None:
        self.out: list[str] = []

    def node(self, node: Node | str, pre: bool = False) -> None:
        if isinstance(node, str):
            self.out.append(escape(node if pre else _SPACES.sub(" ", node)))
            return
        tag = node.tag
        if tag == "table":
            self.table(node)
        elif tag == "br":
            self.out.append("<br>")
        elif tag == "hr":
            self.out.append("<div></div>")
        elif tag in KEEP:
            self.out.append(f"<{tag}>")
            for child in node.children:
                self.node(child, pre or tag == "pre")
            self.out.append(f"</{tag}>")
        elif tag in BLOCKS:
            self.out.append("<div>")
            for child in node.children:
                self.node(child, pre)
            self.out.append("</div>")
        else:
            for child in node.children:
                self.node(child, pre)

    def cell(self, node: Node) -> str:
        inner = _Serializer()
        for child in node.children:
            # Tabelas dentro de células viram texto corrido.
            if isinstance(child, Node) and child.tag == "table":
                inner.out.append(escape(_plain(child)))
            else:
                inner.node(child)
        return "".join(inner.out).strip()

    def table(self, table: Node) -> None:
        rows: list[list[tuple[Node, int]]] = []
        captions: list[str] = []

        def collect(node: Node) -> None:
            for child in node.children:
                if not isinstance(child, Node):
                    continue
                if child.tag == "tr":
                    cells = [
                        (c, _colspan(c))
                        for c in child.children
                        if isinstance(c, Node) and c.tag in ("td", "th")
                    ]
                    if cells and any(_plain(c) for c, _ in cells):
                        rows.append(cells)
                elif child.tag == "caption":
                    captions.append(_plain(child))
                elif child.tag != "table":
                    collect(child)

        collect(table)
        for caption in filter(None, captions):
            self.out.append(f"<p><b>{escape(caption)}</b></p>")
        if not rows:
            return
        widths = _column_widths(rows)
        # Uma tabela por linha: o MuPDF perde linhas quando a tabela quebra de página.
        for index, cells in enumerate(rows):
            css = ' class="table-end"' if index == len(rows) - 1 else ""
            self.out.append(f"<table{css}><tr>")
            column = 0
            for position, (cell, span) in enumerate(cells):
                last = position == len(cells) - 1
                end = len(widths) if last else min(column + span, len(widths))
                width = sum(widths[column:end]) or 1
                tag = "th" if cell.tag == "th" else "td"
                self.out.append(f'<{tag} style="width:{width}%">{self.cell(cell)}</{tag}>')
                column = end
            self.out.append("</tr></table>")


def _colspan(cell: Node) -> int:
    try:
        return max(1, min(int(cell.attrs.get("colspan", "1")), 50))
    except ValueError:
        return 1


def _column_widths(rows: list[list[tuple[Node, int]]]) -> list[int]:
    """Larguras em %, proporcionais ao texto de cada coluna (entre 4 e 40 caracteres)."""
    count = max(sum(span for _, span in cells) for cells in rows)
    lengths = [4] * count
    for cells in rows:
        column = 0
        for cell, span in cells:
            if span == 1 and column < count:
                lengths[column] = max(lengths[column], min(len(_plain(cell)), 40))
            column += span
    total = sum(lengths)
    widths = [max(1, round(100 * n / total)) for n in lengths]
    widths[-1] += 100 - sum(widths)
    return widths


def decode_html(source: SourceFile) -> str:
    data = source.data
    for bom, encoding in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16")):
        if data.startswith(bom):
            return data.decode(encoding, errors="replace")
    candidates = [source.charset]
    match = _META_CHARSET.search(data[:4096])
    if match:
        candidates.append(match.group(1).decode("ascii", errors="ignore"))
    for name in filter(None, candidates):
        try:
            codecs.lookup(name)
        except LookupError:
            continue
        return data.decode(name, errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


@dataclass
class CleanHtml:
    title: str
    html: str
    text: str


def clean_html(markup: str) -> CleanHtml:
    builder = _TreeBuilder()
    builder.feed(markup)
    builder.close()
    serializer = _Serializer()
    serializer.node(builder.root)
    return CleanHtml(
        title=_SPACES.sub(" ", "".join(builder.title_parts)).strip(),
        html="".join(serializer.out),
        text=_plain(builder.root),
    )


EMPTY_PAGE = (
    "Não encontrei texto nesta página. Ela pode carregar o conteúdo por JavaScript; "
    "nesse caso, copie o texto e use “Colar texto”."
)


def render_clean(
    clean: CleanHtml,
    *,
    title: str,
    source_type: str,
    min_chars: int = MIN_TEXT_CHARS,
    empty_message: str = EMPTY_PAGE,
) -> ConvertedDocument:
    """Diagrama o HTML limpo e lê de volta o texto com a posição de cada palavra."""
    if len(clean.text.replace(" ", "")) < min_chars:
        raise ConversionError(empty_message)
    pdf = html_to_pdf(clean.html)
    try:
        extracted = extract_pdf(pdf)
    except PdfReadError as exc:
        raise ConversionError("Não foi possível ler o texto do conteúdo convertido.") from exc
    return ConvertedDocument(title=title, source_type=source_type, pdf=pdf, extracted=extracted)


class HtmlConverter(Converter):
    source_type = "html"
    content_types = ("text/html", "application/xhtml+xml")
    extensions = (".html", ".htm", ".xhtml")

    def sniff(self, data: bytes) -> bool:
        head = data[:1024].lstrip().lower()
        return head.startswith((b"<!doctype html", b"<html")) or b"<body" in head

    def convert(self, source: SourceFile) -> ConvertedDocument:
        clean = clean_html(decode_html(source))
        title = clean.title or source.stem or "Página"
        return render_clean(clean, title=title[:200], source_type=self.source_type)
