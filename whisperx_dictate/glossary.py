import re

_GLOSSARY_HEADER_RE = re.compile(
    r"^(?P<a>from|wrong|misheard|source)(?:\t|\s{2,})(?P<b>to|correct|right|target)\s*$",
    re.IGNORECASE,
)


def load_glossary_tsv(path):
    """Load UTF-8 glossary: column 1 = text the model may emit, column 2 = replacement.

    Separator: tab, or two-or-more spaces (single space inside a phrase is unchanged).
    Lines starting with # are comments.
    """
    pairs = []
    with open(path, encoding="utf-8") as f:
        for i, raw in enumerate(f):
            line = raw.rstrip("\n\r")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if i == 0 and _GLOSSARY_HEADER_RE.match(stripped):
                continue
            if "\t" in line:
                wrong, right = line.split("\t", 1)
            else:
                parts = re.split(r"\s{2,}", stripped, maxsplit=1)
                if len(parts) < 2:
                    continue
                wrong, right = parts[0], parts[1]
            wrong, right = wrong.strip(), right.strip()
            if not wrong:
                continue
            pairs.append((wrong, right))
    return pairs


def _glossary_replacement_order(pairs):
    """Apply longest wrong-string first so phrases win over shared substrings."""
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def apply_glossary(text, pairs):
    if not text or not pairs:
        return text
    for wrong, right in _glossary_replacement_order(pairs):
        if wrong and wrong in text:
            text = text.replace(wrong, right)
    return text


def glossary_initial_prompt(pairs, max_chars=480):
    """Short ASR bias string built only from unique correct (second) column values."""
    if not pairs:
        return None
    seen = set()
    terms = []
    for _, correct in pairs:
        c = (correct or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        terms.append(c)
    if not terms:
        return None
    body = ", ".join(terms)
    prefix = "Proper names and terms: "
    blob = prefix + body
    if len(blob) > max_chars:
        blob = blob[: max_chars - 3].rstrip(", ") + "..."
    return blob
