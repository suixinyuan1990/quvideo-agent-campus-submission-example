# AI 使用记录

## 辅助内容

本仓库由 Cursor 中的 AI 编码助手根据课程要求生成，范围包括：

- `src/scheduling_agent` 的执行循环、观察决策、四个工具、草稿存储、结果汇总和命令行
- `data` 中的合成素材、规则、时段和故障
- `examples` 的输入，以及由程序实际跑出的 `output.json` 和 `trace.json`
- `tests` 与 `docs`

没有把某个线上模型的隐藏推理过程写入轨迹。轨迹里的 `decision_basis` 是决策函数返回的简短依据。

## 生成后的核对与修改

助手在本地执行了：

```powershell
$env:PYTHONPATH = "src"
python -m scheduling_agent.build_examples
python -m pytest -q
```

第一次全量测试有 1 项失败：`test_model_cannot_invent_confirmation` 期望错误码 `hard_requirement_locked`，工具实际先返回 `confirmation_mismatch`。这是安全边界的真实顺序，测试随后改为分别断言“伪造确认”和“未确认却承诺新时间”。当时的结果是 `33 passed`。

示例 JSON 没有手填业务结论。`tests/test_examples_match.py` 会重新运行生成器并比较已提交文件。

## 后续修改与验证

初版生成之后，仍由编码助手按复核意见改过确认边界。这些改动已经在当前文件树里，不是另一套未验证草稿。仓库里没有单独的、助手之外的手工补丁记录。

| 日期 | 文件 | 修改 | 如何验证 |
| --- | --- | --- | --- |
| 2026-11-10 | `src/scheduling_agent/tools.py`、`report.py`、`tests/test_decisions.py` | 新草稿成功写入后，把同一版本上仍待确认的旧草稿标为 `superseded`。不改硬性时间，不写成已发布。保存失败和其他素材不接替 | `python -m pytest -q`，结果 `38 passed in 0.76s`。同一库确认 19:00 后，旧草稿承诺时段仍为空 |
| 2026-11-10 | `docs/02-solution.md`、`docs/03-evaluation.md`、`docs/05-retrospective.md`、`TEST.md` | 把接替行为和审核实测写进方案、评估与回顾。`TEST.md` 是按审核要点重跑后的记录 | 对照 `examples/04`、`examples/05`、`examples/06` 的输出，以及 `tests/test_decisions.py` 的断言 |

当前全量结果：Python 3.12.8、pytest 9.2.0，`38 passed in 0.76s`。示例一致性测试包含在这 38 项里。
