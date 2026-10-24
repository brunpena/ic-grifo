"""PDF com texto: o próprio arquivo vai para o visualizador."""

from app.services.converters.base import ConversionError, ConvertedDocument, Converter, SourceFile
from app.services.pdf_text import PdfReadError, extract_pdf


class PdfConverter(Converter):
    source_type = "pdf"
    content_types = ("application/pdf", "application/x-pdf")
    extensions = (".pdf",)

    def sniff(self, data: bytes) -> bool:
        return data.startswith(b"%PDF-")

    def convert(self, source: SourceFile) -> ConvertedDocument:
        if not self.sniff(source.data):
            raise ConversionError("O arquivo não é um PDF válido.")
        try:
            extracted = extract_pdf(source.data)
        except PdfReadError as exc:
            raise ConversionError(str(exc)) from exc
        title = source.filename or "documento.pdf"
        return ConvertedDocument(
            title=title[:200], source_type=self.source_type, pdf=source.data, extracted=extracted
        )
