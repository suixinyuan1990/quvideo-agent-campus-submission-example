"""运行内容任务规划实例。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.agent.model import ModelDecider, model_configured
from src.agent.planner import ROOT, dump_json, load_json, run_input

CASE_ORDER = [
    "normal",
    "over_budget_switch",
    "no_feasible",
    "missing_info",
    "insufficient_materials",
    "tool_failure",
    "repeat",
    "partial_materials",
    "resume_failed",
    "replan_after_failure",
    "choose_feasible",
]


def write_case(case_dir: Path) -> dict:
    case = load_json(case_dir / "input.json")
    output, trace = run_input(case)
    dump_json(case_dir / "output.json", output)
    dump_json(case_dir / "trace.json", trace)
    saved_path = case_dir / "saved_plan.json"
    saved = None
    if "runs" in output:
        saved = output["runs"][0].get("saved_plan")
    else:
        saved = output.get("saved_plan")
    if saved is None:
        if saved_path.exists():
            saved_path.unlink()
    else:
        dump_json(saved_path, saved)
    return output


def acceptance() -> int:
    coverage = load_json(ROOT / "data" / "coverage.json")
    manifest = []
    for case_id in CASE_ORDER:
        case_dir = ROOT / "examples" / case_id
        output = write_case(case_dir)
        if "runs" in output:
            completed = output["runs"][-1]["completed"]
            total_cost = output["runs"][-1]["total_cost"]
            gap = output["runs"][-1]["gap"]
        else:
            completed = output["completed"]
            total_cost = output["total_cost"]
            gap = output["gap"]
        manifest.append(
            {
                "case_id": case_id,
                "covers": coverage[case_id],
                "input": f"examples/{case_id}/input.json",
                "output": f"examples/{case_id}/output.json",
                "trace": f"examples/{case_id}/trace.json",
                "completed": completed,
                "total_cost": total_cost,
                "gap": gap,
            }
        )
        print(f"{case_id}: completed={completed} total_cost={total_cost}")
    dump_json(ROOT / "examples" / "manifest.json", {"unit": "模拟单位", "cases": manifest})
    return 0


def run_one(args: argparse.Namespace) -> int:
    decider = None
    if args.decider == "model":
        if not model_configured():
            print("未配置 MODEL_API_KEY、MODEL_BASE_URL、MODEL_NAME。本地验收请去掉 --decider model。", file=sys.stderr)
            return 2
        decider = ModelDecider()
    if args.input:
        case = load_json(Path(args.input))
    else:
        if args.budget is None or not args.deadline or not args.theme:
            print("单次规划需要 --theme、--budget 和 --deadline，或使用 --input。", file=sys.stderr)
            return 2
        case = {
            "case_id": "adhoc",
            "theme": args.theme,
            "budget": args.budget,
            "deadline": args.deadline,
            "as_of": "2026-11-10T09:00:00",
            "plan_set": "reference",
        }
    output, trace = run_input(case, decider=decider, persist=args.decider != "model")
    if args.decider == "model":
        target = ROOT / "examples" / "model_runs" / case["case_id"]
        dump_json(target / "input.json", case)
        dump_json(target / "output.json", output)
        dump_json(target / "trace.json", trace)
    elif args.input:
        target = Path(args.input).resolve().parent
        dump_json(target / "output.json", output)
        dump_json(target / "trace.json", trace)
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="内容任务规划实例")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("acceptance")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--input")
    run_parser.add_argument("--theme")
    run_parser.add_argument("--budget", type=int)
    run_parser.add_argument("--deadline")
    run_parser.add_argument("--decider", choices=["local", "model"], default="local")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.cmd == "acceptance":
        return acceptance()
    return run_one(args)


if __name__ == "__main__":
    raise SystemExit(main())
