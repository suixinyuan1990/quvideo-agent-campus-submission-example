# 评估

验收命令：

```bash
python -m src.agent acceptance
python -m unittest discover -s tests -v
python -m src.agent run --theme "春季新品上新" --budget 10 --deadline 2026-11-20
```

2026-11-10 实际结果：

- `acceptance` 写完 11 个本地场景，退出码 0。各场景完成情况和费用合计见下表，索引在 `examples/manifest.json`。
- `unittest` 共 25 项，全部通过。测试分布在 `tests/test_instances.py`、`tests/test_budget_replan.py`、`tests/test_guard_resume.py`、`tests/test_graph_state.py`。
- 单次命令主题「春季新品上新」、预算 10、截止时间 2026-11-20。`completed` 为 true，先估算 12，按 R1 改选替代方案，再估算 8 并保存，费用合计 8。`failed_steps_marked_success` 为 false。

预算、依赖、失败后重规划、按估算择优和磁盘状态的逐步核对写在 `TEST.md`。

## 测试预期与实际结果

| 预期 | 实际 | 文件 |
| --- | --- | --- |
| 预算内直接保存 | 周末门店打卡估算 8，预算 10，已保存，没有改选 | `examples/normal/output.json`、`examples/normal/trace.json` |
| 12 超预算后改选 8 并保存 | 先估算 12，再 `switch`，再估算 8，费用合计 8，保存的是替代方案 | `examples/over_budget_switch/output.json`、`examples/over_budget_switch/trace.json` |
| 三个方案时按估算择优 | 先估算初始方案 12，改选低成本方案并估算 6 后保存。目录里排在中间、估算 15 的方案没有执行 | `examples/choose_feasible/output.json`、`examples/choose_feasible/trace.json` |
| 没有可行方案时返回缺口 | 初始 12、替代 15，未保存。最低估算 12，预算 10，缺口 2。保存步骤是 `not_run`，费用合计 0 | `examples/no_feasible/output.json`、`examples/no_feasible/trace.json` |
| 缺预算不补造 | `budget` 为 null，四个工具都是 `not_run`，原因含「缺少预算」 | `examples/missing_info/output.json`、`examples/missing_info/trace.json` |
| 没有素材 | 检索成功但没有可用素材，后续工具 `not_run`，未保存 | `examples/insufficient_materials/output.json`、`examples/insufficient_materials/trace.json` |
| 工具失败不记成功 | 素材检索 `success`，脚本生成 `failed`，估算和保存 `not_run` | `examples/tool_failure/output.json`、`examples/tool_failure/trace.json` |
| 失败后重规划 | 只让初始方案脚本失败一次；检索结果保留，改选替代方案后费用合计 8。初始脚本仍是 `failed` | `examples/replan_after_failure/output.json`、`examples/replan_after_failure/trace.json` |
| 重复执行不重复计费 | 两次费用合计都是 8，第二次新增 0，步骤为 `skipped`，`prior_status` 为 success | `examples/repeat/output.json`、`examples/repeat/trace.json` |

11 个场景的汇总：

| 场景 | 完成 | 费用合计 |
| --- | --- | --- |
| normal | 是 | 8 |
| over_budget_switch | 是 | 8 |
| no_feasible | 否 | 0 |
| missing_info | 否 | 0 |
| insufficient_materials | 否 | 0 |
| tool_failure | 否 | 0 |
| repeat | 是 | 8 |
| partial_materials | 是 | 8 |
| resume_failed | 是 | 8 |
| replan_after_failure | 是 | 8 |
| choose_feasible | 是 | 6 |

## 部分成功、续跑和守卫

| 预期 | 实际 | 文件 |
| --- | --- | --- |
| 缺详情页时保留已检索素材，并改选能做完的方案 | 检索结果带 `partial: true` 和缺失的「详情页」。改选替代方案后费用合计 8。脚本请求的素材 id 都出现在检索结果里 | `examples/partial_materials/output.json`、`examples/partial_materials/trace.json` |
| 失败后续跑不重跑成功步骤 | 第一次脚本 `failed`、费用 0。第二次素材检索 `skipped`，脚本改为 success，费用合计 8 | `examples/resume_failed/output.json`、`examples/resume_failed/trace.json` |
| 另一次命令沿用磁盘状态 | 同一 `case_id` 连续两次持久化：第二次全部 `skipped`，新增费用 0。续跑时第二次跳过已成功检索，只重试失败脚本，费用合计 8 | `tests/test_graph_state.py`。验收不写 `data/state/` |
| 模型不能保存估算 12 的方案 | 脚本化决策器先提议保存 12。守卫写入 `reject`，随后改选并保存 8 | `examples/model_runs/guard_reject_12/` |
| 模型循环在方案级失败后可以改选 | 初始脚本 `failed` 后，守卫拒绝继续 `continue`。决策器改选替代方案，费用合计 8 | `tests/test_graph_state.py` 的 `test_model_can_switch_after_tool_failure` |

`examples/model_runs/guard_reject_12/` 的 `decision_source` 是 `model`。这条记录用的是脚本化动作，不是在线模型。无法解析的动作在 `tests/test_guard_resume.py` 里会停止，且 `saved_plan` 为空。

未配置 `MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME` 时，`python -m src.agent run --decider model` 退出码为 2，不写基线目录。

## 失败

本次 `acceptance` 和 25 项 `unittest` 没有失败项。命令输出里的 `RequestsDependencyWarning` 来自本机 miniconda 中的 `requests` 版本，项目验收不使用这个包，不影响退出码。

## 限制

- 没有配置可用的模型密钥，因此没有在线模型观察到 12 之后再改选的 Trace。
- 素材和方案来自 `data/plans.json` 的合成目录，不是开放检索。
- 工具调用没有单独计价，费用只等于最终采用方案的估算。被放弃的 12 不会加进费用合计。
- 模型循环和本地规则循环仍是两条实现。本地验收不会在每个工具前额外写 `continue`。两条路径共用 `src/agent/graph.py`：脚本素材来自检索结果；方案级失败后，模型循环把改选交回决策器，守卫拒绝在失败步骤上 `continue`。本地规则会自己改选。
- `acceptance` 不读写 `data/state/`。磁盘续跑只在 `python -m src.agent run` 的本地规则路径，以及 `tests/test_graph_state.py` 的持久化测试里核对。
