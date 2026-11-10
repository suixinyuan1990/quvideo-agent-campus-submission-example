"""Run one script generation and write the trace."""

import argparse
import json
from pathlib import Path

from script_agent.corpus import Corpus
from script_agent.loop import run
from script_agent.model import OpenAIModel, ScriptModel, load_dotenv
from script_agent.rules import load_rules
from script_agent.schema import Request


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成一条有素材依据的短视频脚本")
    parser.add_argument("--theme", default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--audience", default=None)
    parser.add_argument("--platform", default=None)
    parser.add_argument("--style", default=None)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--rules", default=None)
    parser.add_argument("--model", choices=("script", "openai"), default="script")
    parser.add_argument("--out", default="examples/last-run.json")
    args = parser.parse_args(argv)

    if args.model == "openai":
        load_dotenv(".env")
        model = OpenAIModel(
            base_url=_env("MODEL_BASE_URL"),
            api_key=_env("MODEL_API_KEY"),
            model_name=_env("MODEL_NAME"),
        )
    else:
        model = ScriptModel()

    output = run(
        Request(
            theme=args.theme,
            duration_sec=args.duration,
            audience=args.audience,
            platform=args.platform,
            style=args.style,
        ),
        Corpus.load(args.corpus),
        load_rules(args.rules),
        model,
    )
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output.result.status)
    if output.result.estimated_duration_sec is not None:
        print(output.result.estimated_duration_sec)
    return 0


def _env(name: str) -> str:
    import os

    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"缺少环境变量 {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
