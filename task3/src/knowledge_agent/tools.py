from knowledge_agent.corpus import Corpus
from knowledge_agent.textutil import numbers_in, phrases_in, tokenize, window

RRF_K = 60
PATH_LIMIT = 20
FUSE_LIMIT = 20
RETURN_LIMIT = 5
NEAR_TIE = 0.02


class ToolError(Exception):
    def __init__(self, tool: str, message: str):
        super().__init__(message)
        self.tool = tool
        self.message = message


class Toolkit:
    def __init__(self, corpus: Corpus, failures: dict[str, int] | None = None):
        self.corpus = corpus
        self._failures = dict(failures or {})

    def search(self, query: str) -> dict:
        self._maybe_fail("search")
        paths = {
            "bm25": [doc_id for doc_id, _score in self.corpus.bm25_hits(query, PATH_LIMIT)],
            "phrase": [doc_id for doc_id, _score in self.corpus.phrase_hits(query, PATH_LIMIT)],
            "ngram": [doc_id for doc_id, _score in self.corpus.ngram_hits(query, PATH_LIMIT)],
        }
        fused = fuse_paths(paths)
        reranked = rerank(query, fused, self.corpus)
        candidates = []
        for rank, doc_id in enumerate(reranked, start=1):
            document = self.corpus.by_id[doc_id]
            excerpt, complete = window(document.body, query)
            candidates.append(
                {
                    "doc_id": document.doc_id,
                    "version_date": document.version_date,
                    "doc_type": document.doc_type,
                    "scope": document.scope,
                    "priority": document.priority,
                    "excerpt": excerpt,
                    "excerpt_complete": complete,
                    "paths": [name for name, ids in paths.items() if doc_id in ids],
                    "rank": rank,
                }
            )
        return {"ok": True, "tool": "search", "candidates": candidates, "path_ranks": paths}

    def read(self, doc_id: str, query: str = "") -> dict:
        self._maybe_fail("read")
        document = self.corpus.by_id.get(doc_id)
        if document is None:
            return {"ok": True, "tool": "read", "found": False, "doc_id": doc_id}
        text, truncated = clip_body(document.body, query)
        return {
            "ok": True,
            "tool": "read",
            "found": True,
            "doc_id": document.doc_id,
            "version_date": document.version_date,
            "doc_type": document.doc_type,
            "scope": document.scope,
            "priority": document.priority,
            "text": text,
            "truncated": truncated,
        }

    def _maybe_fail(self, tool: str) -> None:
        remaining = self._failures.get(tool, 0)
        if remaining > 0:
            self._failures[tool] = remaining - 1
            raise ToolError(tool, f"{tool} failed")


def fuse_paths(paths: dict[str, list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ids in paths.values():
        for rank, doc_id in enumerate(ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def rerank(query: str, fused: dict[str, float], corpus: Corpus) -> list[str]:
    if not fused:
        return []
    query_tokens = tokenize(query)
    query_numbers = set(numbers_in(query))
    query_phrases = phrases_in(query)
    scored: list[tuple[str, float]] = []
    for doc_id, fused_score in fused.items():
        document = corpus.by_id[doc_id]
        body_tokens = set(tokenize(document.body))
        coverage = 0.0
        if query_tokens:
            coverage = len(set(query_tokens) & body_tokens) / len(set(query_tokens))
        phrase_hits = len(query_phrases & phrases_in(document.body))
        phrase_score = min(phrase_hits, 3) / 3
        if query_numbers:
            present = query_numbers & set(numbers_in(document.body))
            number_score = len(present) / len(query_numbers)
        else:
            number_score = 0.0
        final = fused_score + 0.15 * coverage + 0.1 * phrase_score + 0.1 * number_score
        scored.append((doc_id, final))
    scored.sort(key=lambda item: item[1], reverse=True)
    scored = scored[:FUSE_LIMIT]
    best = scored[0][1]
    if best <= 0:
        return []
    kept = [doc_id for doc_id, score in scored if best - score <= NEAR_TIE or score >= best * 0.9]
    return kept[:RETURN_LIMIT]


def clip_body(body: str, query: str, limit: int = 4000) -> tuple[str, bool]:
    if len(body) <= limit:
        return body, False
    text, _complete = window(body, query, limit)
    return text, True
