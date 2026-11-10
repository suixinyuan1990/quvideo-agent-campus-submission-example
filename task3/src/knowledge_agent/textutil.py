import re

_PUNCT = set(" \t\r\n.,;:!?\"'()[]{}，。！？、；：（）【】《》<>")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    latin: list[str] = []
    cjk: list[str] = []

    def flush_latin() -> None:
        if latin:
            tokens.append("".join(latin))
            latin.clear()

    def flush_cjk() -> None:
        if not cjk:
            return
        word = "".join(cjk)
        tokens.append(word)
        tokens.extend(word[index : index + 2] for index in range(len(word) - 1))
        cjk.clear()

    for char in text.lower():
        if char.isascii() and char.isalnum():
            flush_cjk()
            latin.append(char)
        elif "\u4e00" <= char <= "\u9fff":
            flush_latin()
            cjk.append(char)
        else:
            flush_latin()
            flush_cjk()
    flush_latin()
    flush_cjk()
    return tokens


def normalize_compact(text: str) -> str:
    kept = []
    for char in text.lower():
        if char.isalnum() or ("\u4e00" <= char <= "\u9fff"):
            kept.append(char)
    return "".join(kept)


def char_ngrams(text: str, size: int = 3) -> set[str]:
    compact = normalize_compact(text)
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def numbers_in(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text)


def phrases_in(text: str) -> set[str]:
    found = set(re.findall(r"\d+(?:\.\d+)?\s*(?:天|日|分钟|元|个月)", text))
    found.update(re.findall(r"[£$€]\d+(?:\.\d+)?[a-zA-Z]*", text))
    found.update(token for token in re.findall(r"[A-Za-z]{4,}", text.lower()))
    for piece in re.findall(r"[\u4e00-\u9fff]{4,8}", text):
        found.add(piece)
    return found


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？])\s*|(?<=(?<!\d)[.!?])\s+", text.strip())
    return [part for part in parts if part]


def window(text: str, query: str, limit: int = 180) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, True
    positions = []
    lowered = text.lower()
    for token in tokenize(query):
        if token.isascii():
            pos = lowered.find(token.lower())
        else:
            pos = text.find(token)
        if pos >= 0:
            positions.append(pos)
    anchor = min(positions) if positions else 0
    start = max(0, anchor - 20)
    end = min(len(text), start + limit)
    return text[start:end], False
