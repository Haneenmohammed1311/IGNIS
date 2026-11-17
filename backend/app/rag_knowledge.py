"""Small, dependency-free heading-aware retrieval for local Markdown docs."""

from collections import Counter
from math import log
from pathlib import Path
import re
from threading import Lock

DOCS = Path(__file__).resolve().parents[2] / "docs"
KNOWLEDGE_DIR = DOCS / "knowledge_base"
HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)
TOKEN = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)?")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "between", "by", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "to",
    "was", "what", "when", "where", "which", "why", "with",
}
_lock = Lock()
_cached_signature: tuple[tuple[str, int, int], ...] | None = None
_cached_chunks: list[dict[str, str]] = []


def _files() -> list[Path]:
    return sorted(KNOWLEDGE_DIR.rglob("*.md")) if KNOWLEDGE_DIR.is_dir() else []


def _split_markdown(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    headings = list(HEADING.finditer(text))
    if not headings:
        return [{"id": f"{path.stem}#section-1", "title": path.stem, "text": text.strip()}]

    chunks = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        title = heading.group(2).strip()
        body = text[heading.end():end].strip()
        words = TOKEN.findall(title.lower())
        if words and words[0].isdigit():
            words = words[1:]
        tag = words[0] if words else "section"
        chunks.append({
            "id": f"{path.stem}#{index + 1}_{tag}",
            "title": title,
            "text": f"{title}\n{body}".strip(),
        })
    return chunks


def _load_chunks() -> list[dict[str, str]]:
    global _cached_signature, _cached_chunks
    files = _files()
    signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files)
    with _lock:
        if signature != _cached_signature:
            _cached_chunks = [chunk for path in files for chunk in _split_markdown(path)]
            _cached_signature = signature
        return list(_cached_chunks)


def _tokens(text: str) -> list[str]:
    return [token for token in TOKEN.findall(text.lower()) if token not in STOP_WORDS]


def retrieve(query: str, limit: int = 3) -> list[dict[str, str]]:
    """Return the best local Markdown sections with stable citation IDs."""
    chunks = _load_chunks()
    query_tokens = _tokens(query)
    if not chunks or not query_tokens:
        return []

    document_tokens = [_tokens(chunk["text"]) for chunk in chunks]
    document_frequency = Counter(token for tokens in document_tokens for token in set(tokens))
    scored = []
    for chunk, tokens in zip(chunks, document_tokens):
        frequencies = Counter(tokens)
        score = 0.0
        for token in set(query_tokens):
            frequency = frequencies[token]
            if frequency:
                inverse_frequency = log(1 + (len(chunks) - document_frequency[token] + 0.5)
                                        / (document_frequency[token] + 0.5))
                score += inverse_frequency * (frequency * 2.2) / (frequency + 1.2)
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [dict(chunk) for _, chunk in scored[:max(1, min(limit, 3))]]
