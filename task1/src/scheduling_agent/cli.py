"""命令行入口。在仓库根目录运行。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scheduling_agent.agent import project_root, run_input
from scheduling_agent.catalog import dump_json, load_json
from scheduling_agent.model import make_model
from scheduling_agent.types import ModelConfigError


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(description="审核素材并保存发布排期草稿")
    parser.add_argument("input", help="请求 JSON 路径")
    parser.add_argument("--data-dir", default=None, help="资料目录，默认是仓库 data/")
    parser.add_argument("--store", default=None, help="草稿存储路径，默认是 var/drafts.json")
    parser.add_argument("--output", default=None, help="把交付结果写入该文件")
    parser.add_argument("--trace", default=None, help="把运行记录写入该文件")
    parser.add_argument("--model", choices=["local", "llm"], default="local")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--max-tool-calls", type=int, default=None)
    args = parser.parse_args(argv)

    root = project_root()
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"找不到输入文件：{input_path}", file=sys.stderr)
        return 1
    try:
        payload = load_json(input_path)
    except json.JSONDecodeError:
        print("输入文件不是合法 JSON。", file=sys.stderr)
        return 1
    try:
        model = make_model(args.model)
    except ModelConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    bundle = run_input(
        payload,
        data_dir=args.data_dir or (root / "data"),
        store_path=args.store or (root / "var" / "drafts.json"),
        model=model,
        max_steps=args.max_steps,
        max_tool_calls=args.max_tool_calls,
    )
    output = bundle["output"]
    if args.output:
        dump_json(Path(args.output), output)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    if args.trace:
        dump_json(Path(args.trace), bundle["trace"])
    return exit_code(output)


def exit_code(output: dict[str, Any]) -> int:
    runs = output.get("runs")
    results = runs if isinstance(runs, list) else [output]
    if any(item.get("run_status") == "incomplete" for item in results):
        return 2
    if any(item.get("draft_save_status") == "failed" for item in results):
        return 3
    return 0


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os_environ_set_default(key.strip(), value.strip().strip('"').strip("'"))


def os_environ_set_default(key: str, value: str) -> None:
    import os

    os.environ.setdefault(key, value)


if __name__ == "__main__":
    raise SystemExit(main())
