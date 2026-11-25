"""Localiza um trecho citado dentro de um texto maior.

A IA (ou a seleção feita no navegador) devolve o trecho copiado, mas os espaços e
quebras de linha podem não bater com o texto extraído do PDF. A busca exata vem
primeiro; depois uma busca que trata qualquer sequência de espaços como equivalente.
"""

import re

# Hifens e aspas que costumam mudar entre a extração do PDF e a cópia.
_EQUIVALENT = {
    "‐": "-",
    "‑": "-",
    "–": "-",
    "—": "-",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
}


def _fold(text: str) -> str:
    return "".join(_EQUIVALENT.get(ch, ch) for ch in text)


def find_excerpt(haystack: str, excerpt: str, start: int = 0) -> tuple[int, int] | None:
    """Devolve (início, fim) do trecho em `haystack`, ou None. Offsets em code points."""
    excerpt = excerpt.strip()
    if not excerpt:
        return None
    index = haystack.find(excerpt, start)
    if index >= 0:
        return index, index + len(excerpt)

    # `_fold` troca caractere por caractere, então os offsets continuam valendo.
    folded = _fold(haystack)
    words = _fold(excerpt).split()
    pattern = r"\s+".join(re.escape(w) for w in words)
    match = re.compile(pattern).search(folded, start) or re.compile(pattern, re.IGNORECASE).search(
        folded, start
    )
    return (match.start(), match.end()) if match else None
