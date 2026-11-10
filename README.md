# 四道 Agent 项目题

本仓库包含四道项目题的完整 Python 实现。每个项目都在自己的目录里独立安装和运行，包含源码、资料、自动化测试、实际输入输出与 Trace，以及五份设计文档。

各子项目的 `README.md` 写明环境、安装、CLI、真实模型入口、离线决策边界和已知限制。业务验收数据以合成为主。题 3 另有 FaithEval 冲突段落抽样，题 4 另有 AdvertiseGen 商品属性串。仓库不提交 `.env`，也不包含 API Key 或个人隐私数据。

## 题号

| 题号 | 项目 | 目录 | 入口 |
| --- | --- | --- | --- |
| 1 | 素材审核与发布排期 Agent | [task1/](task1/) | `python -m scheduling_agent` |
| 2 | 内容任务规划 Agent | [task2/](task2/) | `python -m src.agent` |
| 3 | 企业知识问答 Agent | [task3/](task3/) | `python -m knowledge_agent.cli` |
| 4 | 短视频脚本 Agent | [task4/](task4/) | `python -m script_agent.cli` |

Python 3.10 及以上可运行题 1 和题 2。题 3、题 4 的文档按 Python 3.12 记录。四个项目都没有使用 LangChain、LangGraph 或其他 Agent 框架。循环、工具路由和 Trace 都在各自源码里。

## 各题在做什么

### 1. 素材审核与发布排期

内容团队提交一条素材后，程序读取素材、核对审核规则、查询发布时间，并只保存排期草稿。它不会发布。默认决策器 `ObservationDecisionModel` 每看到一次工具结果就重选下一步：补查、建议替代时段、请求确认、阻断或结束。

四个工具是 `read_material`、`check_rules`、`query_slots`、`save_draft`。交付包含审核状态、风险原因、建议时段、待确认项和草稿保存状态。参考实例 M01 要求 18:00，该时段已被占用、19:00 空闲时，结果建议 19:00，`confirmation_status` 为 `pending`，`publish_state` 为 `not_published`。用户未在请求里给出 `confirmed_slot` 时，程序不改硬性发布时间。相同请求再次保存返回已有草稿。

必须覆盖的路径：正常排期、素材信息缺失、规则风险、时段冲突、重复提交、保存失败。另外记录了工具失败、步数上限、工具次数上限、用户确认后改期，以及一次失败补查成功后继续排期。对应文件在 `task1/examples/01-normal/` 到 `task1/examples/11-transient-then-schedule/`。

### 2. 内容任务规划

运营人员给出主题、预算和截止时间后，程序检索合成素材、生成脚本、估算成本，并在检查通过后保存方案。四个工具是素材检索、脚本生成、成本估算、方案保存。费用只来自 `data/plans.json`，模型不能在动作里改价。

估算超过预算或赶不上截止时间时改选仍可执行的方案，或停止并写出缺口。工具失败保留此前成功的步骤。同一输入再次执行时识别已保存方案，费用不重复累计。参考数字：预算 10，初始方案估算 12，改选后估算 8 再保存；被放弃的 12 不进入费用合计。

必须覆盖的路径：正常完成、缺预算或截止时间、工具失败、预算超限、重复执行。已提交场景还包括部分素材、失败后续跑、无可行方案和择优改选，共 11 组，位于 `task2/examples/`。

### 3. 企业知识问答

员工询问制度或产品问题时，程序只依据给定资料作答，并交付回答、文档 ID、版本日期、原文片段、资料缺口和任务状态。两个工具是文档检索和片段读取。引用必须是本轮工具结果里的连续原文。资料冲突时并列双方并请求确认，不选一边当成事实。

验收语料在 `task3/data/policies/`。参考规则是 D01 写报销期限 30 天、D02 写 15 天，且都没有适用范围。问「报销期限多久」时列出冲突，不能回答 15 天。FaithEval inconsistent 使用该题自己的封闭文档池，抽样种子 `20260310`，冲突题和单文档题各 20 道，结果在 `task3/examples/faitheval-sample/summary.json`。

必须通过的六类场景：明确答案、文档冲突、资料外问题、改写后的相似问题、上下文追问、工具失败。样例在 `task3/examples/scenarios/`。

### 4. 短视频脚本

创作者给出主题、受众、平台、目标时长和风格后，程序检索产品素材、估算时长、检查品牌规则，并交回可编辑脚本。三个工具是素材检索、时长估算、规则检查。成功交付同时包含标题、分镜、旁白或字幕、预计总时长、素材来源 ID、风险和任务状态。产品事实只来自检索结果，时长只来自估算工具。

默认命令以主题「详细介绍支持字幕」、目标 30 秒运行：先写出较长稿并估成 38 秒，再压到较短稿并估成 28 秒，引用夹具 P01。缺主题或目标时长时状态为 `needs_input`。检索为空、工具失败、超时后仍无法压到目标时长时，状态写明停在哪里。不生成成片，不剪辑，不配音，不上传，不排期。

必须通过的五类场景：正常生成、缺关键信息、无素材、工具失败、超时长后的修正或明确失败。样例在 `task4/examples/scenarios/`。

## 设计文档

每个项目的 `docs/` 都有同一组五份文档：

| 文件 | 内容 |
| --- | --- |
| `docs/01-requirements.md` | 用户、目标、范围和成功标准 |
| `docs/02-solution.md` | 调用流程、动态决策和技术取舍 |
| `docs/03-evaluation.md` | 测试预期、实际结果、失败和限制 |
| `docs/04-ai-usage.md` | AI 辅助内容、后续修改及验证 |
| `docs/05-retrospective.md` | 最难问题、学习收获、下一步 |

题 1 另有 `TEST.md`。题 2 另有 `PRD.md` 和 `TEST.md`，评审以 `docs/` 与 `examples/` 为准。题 3、题 4 另有 `PRD.md` 和 `TEST.md`。

## 快速评审

下面以题 4 为例。在仓库根目录打开 PowerShell：

```powershell
cd task4
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m pytest
python -m script_agent.cli --theme "详细介绍支持字幕" --duration 30 --audience "功能介绍观众" --platform "抖音" --style "口播" --corpus data/fixtures/materials.jsonl
```

默认剧本模型不访问网络。问答或脚本结果写入该目录的 `examples/last-run.json`。

macOS 或 Linux 把模块路径改成：

```bash
cd task4
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 -m pytest
```

题 4 没有可编辑安装入口。`pip install -e '.[dev]'` 只适用于题 1 的 [task1/pyproject.toml](task1/pyproject.toml)；题 1 文档中的验收命令仍是 `requirements.txt` 加 `PYTHONPATH=src`。

其余三题在各自目录执行：

```powershell
# 题 1：标准库运行时，pytest 只用于测试
cd task1
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m pytest -q
python -m scheduling_agent examples/04-slot-conflict/input.json --store var/m01.json

# 题 2：验收和测试都只用标准库，测试框架是 unittest
cd task2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m src.agent acceptance

# 题 3
cd task3
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m pytest
python -m knowledge_agent.cli --question "报销期限多久？" --corpus data/policies
```

单题的参数、退出码和示例再生方式见该目录的 `README.md`。

## 真实模型与离线决策

未配置密钥时，四题都用本地决策跑完验收，不访问网络。已提交的 `examples/` 来自这些离线路径。配置密钥后，远程调用走 OpenAI 兼容的 Chat Completions，由守卫或结果校验决定能否保存、能否把引用写成已核实。

| 题号 | 离线入口 | 真实模型入口 | 环境变量 |
| --- | --- | --- | --- |
| 1 | 默认 `--model local` | `--model llm` | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` |
| 2 | 三个变量都为空，Trace 中 `decision_source` 为 `local_policy` | `run --decider model`；未配置时退出码 2 | `MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME` |
| 3 | 默认 `--model scripted` | `--model openai` | `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME` |
| 4 | 默认 `--model script` | `--model openai` | `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME` |

题 1、题 2 用标准库 `urllib` 调 `/chat/completions`。题 2 的动作由 function calling 的 `propose_action` 返回。题 3、题 4 使用 `openai` SDK 的 `chat.completions.create`。各题 `.env.example` 中的密钥为空。需要在线模型时，把该文件复制为 `.env` 再填写，且不要提交 `.env`。

各题评估文档写明：本次提交没有用真实密钥做端到端调用。示例轨迹是本地决策的输出。

## 依赖

| 题号 | 运行时 | 测试 |
| --- | --- | --- |
| 1 | Python 标准库 | `pytest>=8` |
| 2 | Python 标准库。可选模型调用也用 `urllib` | 标准库 `unittest`。`requirements.txt` 不安装第三方包 |
| 3 | `pydantic`、`openai`、`rank-bm25` | `pytest>=8` |
| 4 | `pydantic`、`openai`、`rank-bm25` | `pytest>=8` |

## 文档中记录的测试

下列数字来自各题 `docs/03-evaluation.md` 或 `docs/04-ai-usage.md`，环境为 Python 3.12.8。复跑以各目录 README 的命令为准。

| 题号 | 命令 | 记录结果 |
| --- | --- | --- |
| 1 | `python -m pytest -q` | pytest 9.2.0，38 通过 |
| 2 | `python -m unittest discover -s tests -v` | 25 通过。`acceptance` 无失败项 |
| 3 | `python -m pytest` | pytest 9.2.0，10 通过。FaithEval 抽样 40/40。审核 100/100 |
| 4 | `python -m pytest` | pytest 9.2.0，14 通过。审核 100/100 |

## 已知限制

各题评估文档里的边界如下。细节以对应 `docs/03-evaluation.md` 为准。

- 题 1 一次处理一条素材。替代时段只选同一日期中更晚的第一个空闲时刻。默认决策可逐行阅读，本次示例不是在线模型生成的。保存失败示例依赖 `data/tool_faults.json`。
- 题 2 的素材和方案来自 `data/plans.json`，不是开放检索。费用只等于最终采用方案的估算。本地规则循环和模型循环是两条实现，共用 `src/agent/graph.py`。未配置三个模型变量时，没有在线模型看到估算 12 后再改选的 Trace。
- 题 3 的剧本模型在缺限定时拒绝或列出冲突，不主动追问。英文问句不做「所问事实必须出现在原文」的字面拒绝。FaithEval 抽样不检验在全库开放检索中能否同时找回冲突双方。真实模型的引用约束靠系统提示，测试没有调用真实接口。
- 题 4 的五类验收使用剧本模型和 P01 夹具，不对 AdvertiseGen 全量逐条生成。品牌规则只有验收用的固定声明。短于目标时长可以完成，并在风险中写明；最短事实句仍超时则状态为 `unsatisfied`。AdvertiseGen 自带广告文案不可当作产品事实，时长数字只来自估算工具。
