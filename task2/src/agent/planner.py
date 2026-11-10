"""兼容入口。实现位于编排器、工具、守卫和决策器。"""

from src.agent.files import ROOT, dump_json, load_json
from src.agent.orchestrator import run_input

__all__ = ["ROOT", "dump_json", "load_json", "run_input"]
