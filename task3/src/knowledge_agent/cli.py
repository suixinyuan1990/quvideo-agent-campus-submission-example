import argparse
import json
from pathlib import Path

from knowledge_agent.corpus import Corpus
from knowledge_agent.loop import run_question
from knowledge_agent.model import model_from_env
from knowledge_agent.tools import Toolkit


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="企业知识问答")
    parser.add_argument("--question", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--history", default="")
    parser.add_argument("--model", choices=("scripted", "openai"), default="scripted")
    parser.add_argument("--output", default="examples/last-run.json")
    args = parser.parse_args(argv)
    history = []
    if args.history:
        history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    corpus = Corpus.load(args.corpus)
    result = run_question(args.question, history, Toolkit(corpus), model_from_env(args.model))
    payload = {
        "input": {"question": args.question, "history": history, "corpus": args.corpus},
        "output": result.answer.model_dump(),
        "trace": [event.model_dump() for event in result.trace],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result.answer.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
