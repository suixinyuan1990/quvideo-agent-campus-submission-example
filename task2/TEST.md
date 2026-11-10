# 测试记录

核对预算计算、步骤依赖和实际状态，并注入一次失败，看计划会不会改、已经成功的结果还在不在。命令：

```bash
python -m src.agent acceptance
python -m unittest discover -s tests -v
```

2026-11-10 的结果：`acceptance` 写完 11 个本地场景；`unittest` 共 25 项，全部通过。结论下面都指向这次生成的文件。

## 预算计算

费用只来自成本估算工具返回的明细：素材费用 + 脚本费用。被放弃的估算不进费用合计。未保存时费用合计为 0，缺口另记。

| 核对项 | 实际 | 文件 |
| --- | --- | --- |
| 初始方案 7 + 5 | 估算 12，预算 10，超出 2 | `examples/over_budget_switch/trace.json` |
| 替代方案 4 + 4 | 估算 8，超出 0，随后保存 | 同上 |
| 费用合计 | 8，不是 12，也不是 12 + 8 | `examples/over_budget_switch/output.json` |
| 两个方案都超预算 | 12 与 15，最低 12，缺口 2，费用合计 0，未保存 | `examples/no_feasible/output.json` |

对应测试：`tests/test_budget_replan.py` 中的 `test_reference_budget_matches_breakdown_and_does_not_add_rejected_plan`、`test_no_feasible_gap_is_lowest_minus_budget`。

## 步骤依赖与实际状态

依赖是：

1. 素材检索不依赖某一个方案，成功结果供后续方案共用。
2. 某个方案的脚本生成依赖这次检索，并且只使用检索结果里的素材 id。请求带 `source: material_search`。
3. 某个方案的成本估算依赖该方案脚本成功，费用只计检索结果里的素材。脚本失败时，不为这个方案估算，也不保存。
4. 保存依赖估算同时满足预算和截止时间。保存的素材同样只来自检索结果。

只剩一个方案且脚本失败时，状态停在失败，不把失败改成成功：`examples/tool_failure/output.json` 里检索是 `success`，脚本是 `failed`，估算和保存是 `not_run`。这能证明失败有记录，但还不能证明会重规划。

## 注入一次失败后的重规划

场景 `examples/replan_after_failure/`。预算 10。初始方案目录价是 12，替代方案是 8。只给初始方案的脚本生成注入一次失败，替代方案的工具不失败。

实际顺序见 `examples/replan_after_failure/output.json` 和 `examples/replan_after_failure/trace.json`：

| 步骤 | 实际状态 |
| --- | --- |
| 素材检索 | `success`，结果保留 |
| 初始方案脚本生成 | `failed`，返回「脚本生成失败」，没有被改成 success |
| 初始方案成本估算、保存 | 没有执行。估算依赖脚本，失败方案没有产生 12 的费用 |
| 决策 | `switch`，规则 R3：「初始方案的脚本生成失败。已成功的素材检索结果保留，改选替代方案。」`retained` 为 `material_search` |
| 替代方案脚本、估算、保存 | 均为 `success`。估算 4 + 4 = 8，不超过预算 10 |
| 费用合计 | 8，已保存替代方案 |

这次运行是同一次规划里的状态，不是事后再开一轮。检索没有重做，失败步骤仍是 `failed`。

没有替代方案时仍然停止，见 `examples/tool_failure/`。共享的素材检索如果失败，后续方案都无法开始，也会停止。

## 优化

规则 R3 从「失败后一律停止保存」改为：失败只阻断当前方案、并且还有替代方案时，保留已成功结果并改选；否则停止。脚本失败、估算失败、保存失败都走这条规则。改选后的方案仍要重新估算，超预算不能保存。

实现在 `src/agent/orchestrator.py` 和 `src/agent/graph.py`。按方案注入失败用 `data/plans.json` 的 `fail_plan_tools`，不把整个工具标成永远失败，否则替代方案也会被同一处故障拦住，重规划无法发生。

## 按依赖和估算择优

场景 `examples/choose_feasible/`。预算 10。三个方案的目录估算依次是初始 12、高成本 15、低成本 6，素材都能检索到。

实际顺序见 `examples/choose_feasible/output.json` 和 `examples/choose_feasible/trace.json`：

| 步骤 | 实际 |
| --- | --- |
| 初始方案 | 先按列表顺序估算，得到 12，超过预算 10 |
| 改选 | `switch`，`to_plan` 为 `lean`，`reason_code` 为 `budget`。没有改去目录里的下一个高成本方案 |
| 高成本方案 | 没有执行成本估算 |
| 低成本方案 | 估算 3 + 3 = 6，保存，费用合计 6 |

第一个方案仍按列表顺序执行，所以参考实例 `examples/over_budget_switch/` 仍然先看到 12，再改到唯一剩下的 8。

## 磁盘状态

`python -m src.agent run` 的本地规则把状态写到 `data/state/<case_id>.json`。验收和普通单元测试不写这些文件。

`tests/test_graph_state.py` 里的两次 `persist=True`：

| 核对 | 实际 |
| --- | --- |
| 第二次命令沿用已保存方案 | 步骤全部 `skipped`，新增费用 0，费用合计仍是 8 |
| 第二次命令续跑 | 第一次脚本 `failed`、费用 0；第二次检索 `skipped`，脚本 success，费用合计 8 |

`over_budget_switch` 和 `repeat` 的主题、预算、截止时间和 `plan_set` 相同，磁盘文件按 `case_id` 分开。

## 模型循环里的方案级失败

脚本化决策器跑 `replan_script`：初始方案脚本失败后，守卫拒绝继续 `continue`。决策器改选替代方案，检索结果保留，费用合计 8，初始脚本仍是 `failed`。见 `tests/test_graph_state.py` 的 `test_model_can_switch_after_tool_failure`。共享检索失败时仍然停止。
