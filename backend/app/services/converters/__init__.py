"""Conversores de documento: PDF, HTML e texto (o link baixa o arquivo e escolhe um deles)."""

from app.services.converters.base import (
    ConversionError,
    ConvertedDocument,
    Converter,
    SourceFile,
    UnsupportedFormatError,
)
from app.services.converters.registry import ConverterRegistry, registry

__all__ = [
    "ConversionError",
    "ConvertedDocument",
    "Converter",
    "ConverterRegistry",
    "SourceFile",
    "UnsupportedFormatError",
    "registry",
]
