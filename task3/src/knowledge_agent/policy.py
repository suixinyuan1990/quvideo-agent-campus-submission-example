import re
from difflib import SequenceMatcher

from knowledge_agent.schema import Action, Answer, Citation
from knowledge_agent.textutil import contains_cjk, numbers_in, sentences, tokenize

MAX_ACTIONS = 6


def build_search_query(question: str, history: list[dict]) -> str:
    previous = [turn["content"] for turn in history if turn.get("role") == "user"]
    if previous and re.search(r"那|这|呢|它|此", question):
        return f"{previous[-1]} {question}"
    return question


def next_action(state: dict) -> Action:
    if state["guard_feedback"]:
        return Action(action="finish", result=decide(state), reason="根据校验结果修正交付")
    observations = state["observations"]
    searches = successful_searches(observations)
    if not searches:
        return Action(action="search", query=build_search_query(state["question"], state["history"]), reason="检索资料")
    candidates = searches[-1]["output"]["candidates"]
    if not candidates:
        return Action(action="finish", result=missing_answer(state["question"]), reason="没有相关文档")
    pending = docs_still_needed(candidates, observations)
    slots_left = MAX_ACTIONS - len(observations) - 1
    if pending and slots_left > 0:
        return Action(action="read", doc_id=pending[0], reason="核对原文或冲突")
    return Action(action="finish", result=decide(state), reason="证据已足够")


def decide(state: dict) -> Answer:
    question = state["question"]
    docs = read_documents(state["observations"])
    if not docs:
        docs = documents_from_search(state["observations"])
    docs = [document for document in docs if document_supports(question, document["text"])]
    if not docs:
        return missing_answer(question)
    conflict = find_conflict(docs, question)
    if conflict is not None:
        return conflict_answer(question, conflict)
    chosen = select_document(docs, question)
    lead = best_sentence(chosen["text"], question)
    citation = Citation(doc_id=chosen["doc_id"], version_date=chosen["version_date"], excerpt=chosen["text"])
    if contains_cjk(question):
        answer = f"根据 {chosen['doc_id']}，{lead}"
    else:
        answer = f"According to {chosen['doc_id']}, {lead}"
    return Answer(answer=answer, citations=[citation], gaps=[], status="answered")


def missing_answer(question: str) -> Answer:
    if contains_cjk(question):
        answer = "现有资料不能回答该问题。"
        gap = "缺少与该问题相关的制度或产品资料。"
    else:
        answer = "The available documents do not answer this question."
        gap = "Missing a document that covers this question."
    return Answer(answer=answer, citations=[], gaps=[gap], status="insufficient_evidence")


def successful_searches(observations: list[dict]) -> list[dict]:
    return [
        item
        for item in observations
        if item["action"] == "search" and item["output"] and item["output"].get("ok") and "candidates" in item["output"]
    ]


def docs_still_needed(candidates: list[dict], observations: list[dict]) -> list[str]:
    read_ids = {
        item["arguments"].get("doc_id")
        for item in observations
        if item["action"] == "read" and item["output"] and item["output"].get("found")
    }
    needed = []
    multiple = len(candidates) >= 2
    for candidate in candidates:
        doc_id = candidate["doc_id"]
        if doc_id in read_ids:
            continue
        if multiple or not candidate.get("excerpt_complete", False):
            needed.append(doc_id)
    return needed


def read_documents(observations: list[dict]) -> list[dict]:
    documents = []
    for item in observations:
        output = item.get("output") or {}
        if item["action"] == "read" and output.get("found") and output.get("text"):
            documents.append(
                {
                    "doc_id": output["doc_id"],
                    "version_date": output.get("version_date"),
                    "scope": output.get("scope"),
                    "priority": output.get("priority"),
                    "text": output["text"],
                }
            )
    return documents


def documents_from_search(observations: list[dict]) -> list[dict]:
    searches = successful_searches(observations)
    if not searches:
        return []
    documents = []
    for candidate in searches[-1]["output"]["candidates"]:
        documents.append(
            {
                "doc_id": candidate["doc_id"],
                "version_date": candidate.get("version_date"),
                "scope": candidate.get("scope"),
                "priority": candidate.get("priority"),
                "text": candidate["excerpt"],
            }
        )
    return documents


def find_conflict(docs: list[dict], question: str) -> tuple[dict, dict, str, str] | None:
    for left_index, left in enumerate(docs):
        for right in docs[left_index + 1 :]:
            pair = conflicting_excerpts(left, right, question)
            if pair is not None:
                return (left, right, pair[0], pair[1])
    comparable = [document for document in docs if not document.get("scope") and not document.get("priority")]
    comparable = [document for document in comparable if not resolves_conflict(document["text"])]
    if len(comparable) < 2:
        return None
    ranked = sorted(comparable, key=lambda document: relevance(document["text"], question), reverse=True)
    if relevance(ranked[0]["text"], question) < 0.02:
        return None
    if relevance(ranked[0]["text"], question) - relevance(ranked[1]["text"], question) > 0.35:
        return None
    if same_claim(ranked[0]["text"], ranked[1]["text"]):
        return None
    left_excerpt = best_sentence(ranked[0]["text"], question)
    right_excerpt = best_sentence(ranked[1]["text"], question)
    return (ranked[0], ranked[1], left_excerpt, right_excerpt)


def conflicting_excerpts(left: dict, right: dict, question: str) -> tuple[str, str] | None:
    if left.get("scope") or right.get("scope") or left.get("priority") or right.get("priority"):
        return None
    if resolves_conflict(left["text"]) or resolves_conflict(right["text"]):
        return None
    ratio = SequenceMatcher(None, left["text"], right["text"]).ratio()
    if ratio < 0.55:
        return None
    excerpts = diff_excerpts(left["text"], right["text"])
    if excerpts is None or same_claim(excerpts[0], excerpts[1]):
        return None
    return excerpts


def same_claim(left: str, right: str) -> bool:
    return _COMPACT.sub("", left) == _COMPACT.sub("", right)


def document_supports(question: str, text: str) -> bool:
    if scope_blocks(question, text):
        return False
    if not contains_cjk(question):
        return True
    chunks = content_chunks(question)
    if not chunks:
        return True
    return all(chunk_supported(chunk, text) for chunk in chunks)


def content_chunks(question: str) -> list[str]:
    cleaned = re.sub(r"[？?！!，,。.\s]", "", question)
    parts = [part for part in _QUESTION_WORDS.split(cleaned) if len(part) >= 2]
    return [part for part in parts if part not in _QUESTION_WORD_SET]


def chunk_supported(chunk: str, text: str) -> bool:
    core = re.sub(r"^[那这此]+", "", chunk)
    core = re.sub(r"[后时里中内吗呢吧啊]+$", "", core)
    if len(core) < 2:
        return True
    match = longest_match(core, text)
    if match is None:
        return False
    start, end = match
    prefix = core[:start].strip("后时里中内")
    suffix = core[end:].strip("后时里中内")
    if len(prefix) >= 2 and prefix not in text:
        return False
    if len(suffix) >= 2 and suffix not in text:
        return False
    return True


def longest_match(chunk: str, text: str) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    for start in range(len(chunk)):
        for end in range(start + 2, len(chunk) + 1):
            if chunk[start:end] in text and (best is None or end - start > best[1] - best[0]):
                best = (start, end)
    return best


def scope_blocks(question: str, text: str) -> bool:
    if inapplicable(text, question):
        return True
    match = re.search(r"只适用于([^。；;]{2,16})", text)
    if match is None:
        return False
    scope = match.group(1)
    if scope in question:
        return False
    return not any(scope[:size] in question for size in range(2, len(scope) + 1))


_COMPACT = re.compile(r"[\s，,。；;]")
_QUESTION_WORDS = re.compile(
    r"请问|有没有|是不是|能不能|能否|会不会|要不要|多少|多久|几天|几个|如何|怎么|怎样|是否|什么|哪些|可以|需要|吗|呢|吧|的|了|是|有|和|或|与|及|在|把|被|将|对|到"
)
_QUESTION_WORD_SET = set(_QUESTION_WORDS.pattern.split("|"))


def resolves_conflict(text: str) -> bool:
    return any(marker in text for marker in ("废止", "以较新", "优先适用", "precedence", "supersede"))


def diff_excerpts(left: str, right: str) -> tuple[str, str] | None:
    matcher = SequenceMatcher(None, left, right)
    best: tuple[int, str, str] | None = None
    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if tag != "replace":
            continue
        left_piece = left[left_start:left_end].strip()
        right_piece = right[right_start:right_end].strip()
        if len(left_piece) < 1 or len(right_piece) < 1:
            continue
        if left_piece == right_piece:
            continue
        size = len(left_piece) + len(right_piece)
        if best is None or size > best[0]:
            best = (size, sentence_containing(left, left_piece), sentence_containing(right, right_piece))
    if best is None:
        return None
    return best[1], best[2]


def sentence_containing(text: str, piece: str) -> str:
    for sentence in sentences(text):
        if piece in sentence:
            return sentence
    return piece


def relevance(text: str, question: str) -> float:
    tokens = {token for token in tokenize(question) if len(token) >= 2}
    if not tokens:
        return 0
    overlap = 0
    for token in tokens:
        present = token in text.lower() if token.isascii() else token in text
        if present:
            overlap += 1
    value = overlap / len(tokens)
    if inapplicable(text, question):
        value -= 0.6
    return value


def select_document(docs: list[dict], question: str) -> dict:
    def score(document: dict) -> float:
        value = relevance(document["text"], question)
        if document.get("scope") and document["scope"] in question:
            value += 0.4
        return value

    return max(docs, key=score)


def inapplicable(text: str, question: str) -> bool:
    generic = {"员工", "制度", "规定", "公司", "申请", "年假", "带薪", "每年", "入职", "报销", "期限"}
    for token in set(tokenize(question)):
        if token.isascii() or len(token) < 2 or token in generic:
            continue
        window = rf"{re.escape(token)}.{{0,12}}不适用"
        if re.search(window, text):
            return True
    return False


def best_sentence(text: str, question: str) -> str:
    choices = sentences(text) or [text]
    tokens = {token for token in tokenize(question) if len(token) >= 2}

    def score(sentence: str) -> tuple[int, int, int]:
        overlap = sum(token in sentence.lower() if token.isascii() else token in sentence for token in tokens)
        return (overlap, len(numbers_in(sentence)), len(sentence))

    return max(choices, key=score)


def conflict_answer(question: str, conflict: tuple[dict, dict, str, str]) -> Answer:
    left, right, left_excerpt, right_excerpt = conflict
    citations = [
        Citation(doc_id=left["doc_id"], version_date=left["version_date"], excerpt=left_excerpt),
        Citation(doc_id=right["doc_id"], version_date=right["version_date"], excerpt=right_excerpt),
    ]
    date_note = later_version_note(left, right, question)
    if contains_cjk(question):
        lines = ["检索到的文档互相冲突，不能确定唯一答案。"]
        for document, excerpt in ((left, left_excerpt), (right, right_excerpt)):
            lines.append(f"{document['doc_id']}：{excerpt}")
        if date_note:
            lines.append(date_note)
        lines.append("请确认适用哪一份文档。")
        gap = "未说明哪一份文档优先，缺少效力规则。"
    else:
        lines = ["The retrieved documents conflict, so there is no single answer."]
        for document, excerpt in ((left, left_excerpt), (right, right_excerpt)):
            lines.append(f"{document['doc_id']}: {excerpt}")
        if date_note:
            lines.append(date_note)
        lines.append("Please confirm which document applies.")
        gap = "The documents do not state which one takes precedence."
    return Answer(answer="\n".join(lines), citations=citations, gaps=[gap], status="conflict")


def later_version_note(left: dict, right: dict, question: str) -> str:
    left_date = left.get("version_date")
    right_date = right.get("version_date")
    if not left_date or not right_date or left_date == right_date:
        return ""
    later = left if left_date > right_date else right
    if contains_cjk(question):
        return f"{later['doc_id']} 的版本日期较晚，但版本日期不能单独作为采用依据。"
    return f"{later['doc_id']} has the later version date, but the date alone does not decide which document applies."
