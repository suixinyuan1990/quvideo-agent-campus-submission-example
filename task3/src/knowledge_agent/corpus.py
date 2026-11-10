import json
from pathlib import Path

from pydantic import BaseModel
from rank_bm25 import BM25Okapi

from knowledge_agent.textutil import char_ngrams, phrases_in, tokenize


class Document(BaseModel):
    doc_id: str
    version_date: str | None = None
    doc_type: str
    body: str
    scope: str | None = None
    priority: str | None = None


class Corpus:
    def __init__(self, documents: list[Document]):
        self.documents = documents
        self.by_id = {document.doc_id: document for document in documents}
        self._tokens = [tokenize(document.body) for document in documents]
        self._phrases = [phrases_in(document.body) for document in documents]
        self._ngrams = [char_ngrams(document.body) for document in documents]
        self._bm25 = BM25Okapi(self._tokens) if documents else None

    @classmethod
    def load(cls, path: str | Path, allow_ids: set[str] | None = None) -> "Corpus":
        source = Path(path)
        if source.is_dir():
            source = source / "documents.jsonl"
        documents: list[Document] = []
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            if allow_ids is not None and raw["doc_id"] not in allow_ids:
                continue
            documents.append(Document.model_validate(raw))
        return cls(documents)

    def subset(self, allow_ids: set[str] | list[str]) -> "Corpus":
        allowed = set(allow_ids)
        return Corpus([document for document in self.documents if document.doc_id in allowed])

    def bm25_hits(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(
            ((document.doc_id, float(score)) for document, score in zip(self.documents, scores) if score > 0),
            key=lambda item: item[1],
            reverse=True,
        )
        return ranked[:limit]

    def phrase_hits(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        wanted = phrases_in(query)
        if not wanted:
            return []
        scored = []
        for document, phrases in zip(self.documents, self._phrases):
            overlap = wanted & phrases
            if overlap:
                scored.append((document.doc_id, float(len(overlap))))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def ngram_hits(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        wanted = char_ngrams(query)
        if not wanted:
            return []
        scored = []
        for document, grams in zip(self.documents, self._ngrams):
            if not grams:
                continue
            overlap = len(wanted & grams) / len(wanted)
            if overlap > 0:
                scored.append((document.doc_id, overlap))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]
