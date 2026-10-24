"""Interface comum dos conversores de documento.

Todo conversor entrega a mesma estrutura: um PDF para o visualizador e o texto com a
posição de cada palavra (`ExtractedDocument`). Formatos sem páginas (texto, HTML) são
diagramados em PDF antes, então o grifo, a busca e a ligação regra → trecho funcionam
igual para qualquer origem.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import ClassVar

from app.services.pdf_text import ExtractedDocument


class ConversionError(Exception):
    """O conteúdo não pôde ser convertido. A mensagem, em português, vai para a pessoa."""


class UnsupportedFormatError(ConversionError):
    """Nenhum conversor aceita o conteúdo."""


@dataclass
class SourceFile:
    """Conteúdo recebido, com o que se sabe sobre ele (do upload ou do download)."""

    data: bytes
    filename: str | None = None
    # Sem parâmetros e em minúsculas (ex.: "text/html").
    content_type: str | None = None
    # Codificação declarada pelo servidor ou pelo navegador, se houver.
    charset: str | None = None

    @property
    def extension(self) -> str:
        return PurePosixPath(self.filename or "").suffix.lower()

    @property
    def stem(self) -> str:
        return PurePosixPath(self.filename or "").stem


@dataclass
class ConvertedDocument:
    title: str
    # Formato de origem, gravado em `documents.source_type`.
    source_type: str
    # O PDF exibido no visualizador: o original ou o diagramado a partir do conteúdo.
    pdf: bytes
    extracted: ExtractedDocument


class Converter(ABC):
    """Um formato de entrada. Registre novas implementações em `converters.registry`."""

    source_type: ClassVar[str]
    content_types: ClassVar[tuple[str, ...]] = ()
    extensions: ClassVar[tuple[str, ...]] = ()

    def sniff(self, data: bytes) -> bool:
        """Reconhece o formato pelo conteúdo, quando o tipo e a extensão não ajudam."""
        return False

    @abstractmethod
    def convert(self, source: SourceFile) -> ConvertedDocument:
        """Converte o conteúdo. Síncrono e pesado: chame com `asyncio.to_thread`."""
