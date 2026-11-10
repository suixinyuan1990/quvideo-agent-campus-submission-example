"""In-memory product materials. Reference ad copy is not indexed."""

import json
from pathlib import Path

from rank_bm25 import BM25Okapi

from script_agent.schema import Attribute, Hit, Material
from script_agent.textutil import spoken_text


def _attributes_from_body(body: str) -> list[Attribute]:
    if "#" not in body:
        return []
    pairs: list[Attribute] = []
    for part in body.split("*"):
        if "#" not in part:
            return []
        key, value = part.split("#", 1)
        if not key or not value:
            return []
        pairs.append(Attribute(key=key, value=value))
    return pairs


def _bigrams(text: str) -> list[str]:
    chars = spoken_text(text)
    if len(chars) < 2:
        return [chars] if chars else []
    return [chars[index : index + 2] for index in range(len(chars) - 1)]


def _doc_tokens(material: Material) -> list[str]:
    tokens = _bigrams(material.body)
    tokens.extend(attribute.value for attribute in material.attributes if attribute.value)
    return tokens or [material.body]


class Corpus:
    def __init__(self, materials: list[Material]) -> None:
        self.materials = materials
        self.by_id = {item.source_id: item for item in materials}
        tokenized = [_doc_tokens(item) for item in materials]
        self._tokens = tokenized
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    @classmethod
    def load(cls, path: Path | str) -> "Corpus":
        materials: list[Material] = []
        source = Path(path)
        with source.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("citable") is False or "body" not in row:
                    raise ValueError(f"{source}:{line_number} 没有可引用正文，不能进入检索索引")
                attributes = [Attribute.model_validate(item) for item in row.get("attributes") or []]
                if not attributes:
                    attributes = _attributes_from_body(row["body"])
                materials.append(
                    Material(
                        source_id=row["source_id"],
                        body=row["body"],
                        attributes=attributes,
                        split=row.get("split"),
                        row_index=row.get("row_index"),
                        dataset=row.get("dataset"),
                    )
                )
        return cls(materials)

    def search(self, query: str, limit: int = 5) -> list[Hit]:
        query = query.strip()
        if not query or not self.materials or self._bm25 is None:
            return []
        query_tokens = _bigrams(query)
        scored: list[Hit] = []
        bm25_scores = self._bm25.get_scores(query_tokens or [query])
        for index, material in enumerate(self.materials):
            matched = [
                attribute.value
                for attribute in material.attributes
                if len(attribute.value) >= 2 and attribute.value in query
            ]
            doc_tokens = set(self._tokens[index])
            overlap = any(token in doc_tokens for token in query_tokens)
            if not overlap and not matched:
                continue
            score = float(bm25_scores[index]) + 10.0 * len(matched)
            scored.append(
                Hit(
                    source_id=material.source_id,
                    body=material.body,
                    attributes=material.attributes,
                    matched_values=matched,
                    score=score,
                )
            )
        scored.sort(key=lambda hit: (-hit.score, hit.source_id))
        return scored[:limit]
