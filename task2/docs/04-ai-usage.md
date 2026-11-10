# AI 使用说明

## AI 辅助内容

本仓库的 README、PRD、规划代码、合成数据、实例、测试和 `docs/` 下这五份说明，都是在 Cursor 里由编码助手根据使用者当次对话中的要求生成的。本文这次补充也是同一助手按项目当前实现写的，不是事后另写的一份人工说明。

使用者给出的约束包括：

- 内容任务规划 Agent 的用户、四个工具、交付物和动态决策
- 项目目录和验证材料格式：README、`src/`、`tests/`、`examples/`、`data/`、`docs/01` 至 `docs/05`、依赖文件、`.env.example`
- 参考实例：预算 10，初始估算 12，替代估算 8；没有可行方案时返回缺口；失败步骤不能记为成功
- 先写 README 和 PRD，再按文档实现
- 核对预算、步骤依赖和状态，注入一次失败，看计划是否调整并保留成功结果
- 把依赖图、检索结果传递、按估算择优、磁盘状态和模型循环的失败处理做进项目，并写入文档、完成测试
- 最终目录按评审格式对齐：README 写环境、安装、运行和评审入口；`docs/01` 至 `docs/05` 分别写需求、方案、评估、AI 使用和回顾；`requirements.txt` 与 `.env.example` 写明本地验收无第三方包、无需配置密钥

助手据此实现了本地规则、模块拆分、守卫、可选模型客户端、部分成功、失败续跑，以及依赖图、检索结果传递、按估算择优、按 `case_id` 持久化状态。验收基线由 `python -m src.agent acceptance` 重新生成。最后一次文档对齐没有改规划代码。

## 个人修改

到本次提交为止，没有另附一份人工改过的差异记录。规则、文案、合成数据和测试都来自上述对话中的要求，以及助手按这些要求生成的实现。若之后手工改了规则、文案或数据，应在这里补上改了哪一处、为什么改。

## 验证

在项目根目录实际执行：

```bash
python -m src.agent acceptance
python -m unittest discover -s tests -v
python -m src.agent run --theme "春季新品上新" --budget 10 --deadline 2026-11-20
python -m src.agent run --decider model --theme "春季新品上新" --budget 10 --deadline 2026-11-20
```

2026-11-10 的结果：

- `acceptance` 退出码 0，11 个场景与 `docs/03-evaluation.md` 的汇总表一致。
- `unittest` 为 25 项，全部通过。
- 单次本地规划完成，先估算 12，改选后保存 8，费用合计 8。
- `--decider model` 因未配置 `MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME` 退出码为 2，基线实例没有被改写。

对照过的结果：

- `examples/over_budget_switch/`：先 12，后改选，再 8，然后保存
- `examples/choose_feasible/`：先 12，改选估算 6 的方案并保存，估算 15 的方案没有执行
- `examples/no_feasible/`：缺口 2，未保存，费用合计 0
- `examples/missing_info/`：四个工具均为 `not_run`
- `examples/tool_failure/`：脚本步骤为 `failed`
- `examples/replan_after_failure/`：初始脚本 `failed`，检索结果保留，费用合计 8
- `examples/repeat/`：第二次新增费用 0
- `examples/model_runs/guard_reject_12/`：保存 12 的提议被守卫拒绝，最终保存的是 8
