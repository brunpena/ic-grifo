"""Registro dos conversores. Um formato novo entra criando um `Converter` e registrando-o
aqui; o upload, o link e o processamento não mudam."""

from app.services.converters.base import (
    ConvertedDocument,
    Converter,
    SourceFile,
    UnsupportedFormatError,
)
from app.services.converters.html import HtmlConverter
from app.services.converters.pdf import PdfConverter
from app.services.converters.text import TextConverter

# Tipos que não dizem nada sobre o conteúdo; nesses casos valem a extensão e os bytes.
GENERIC_TYPES = {"application/octet-stream", "binary/octet-stream", "application/unknown"}


class ConverterRegistry:
    def __init__(self) -> None:
        self._converters: list[Converter] = []

    def register(self, converter: Converter) -> None:
        self._converters.append(converter)

    @property
    def converters(self) -> tuple[Converter, ...]:
        return tuple(self._converters)

    def find(self, source: SourceFile) -> Converter | None:
        """Pelo content-type; senão pela extensão; senão pelos primeiros bytes."""
        content_type = source.content_type
        if content_type and content_type not in GENERIC_TYPES:
            for converter in self._converters:
                if content_type in converter.content_types:
                    return converter
        for converter in self._converters:
            if source.extension and source.extension in converter.extensions:
                return converter
        for converter in self._converters:
            if converter.sniff(source.data):
                return converter
        return None

    def convert(self, source: SourceFile) -> ConvertedDocument:
        converter = self.find(source)
        if converter is None:
            raise UnsupportedFormatError(self.unsupported_message(source))
        return converter.convert(source)

    def unsupported_message(self, source: SourceFile) -> str:
        kind = source.extension or source.content_type or "desconhecido"
        accepted = ", ".join(sorted({e for c in self._converters for e in c.extensions}))
        return f"Formato não suportado ({kind}). Envie um destes: {accepted}."


registry = ConverterRegistry()
registry.register(PdfConverter())
registry.register(HtmlConverter())
registry.register(TextConverter())
