# 内容任务规划 Agent

帮助运营人员在预算和截止时间内完成一份内容活动方案。本文是环境、安装、运行和评审入口。用户、范围和成功标准在 [docs/01-requirements.md](docs/01-requirements.md)。

## 环境

- 操作系统：Windows、macOS 或 Linux
- Python：3.10 及以上
- 依赖：见项目根目录 `requirements.txt`。本地规划、验收和测试只用标准库，不安装第三方包

外部模型使用 OpenAI 兼容接口。复制 `.env.example` 为 `.env` 后，只有三个变量都有值才调用：

| 变量 | 含义 |
| --- | --- |
| `MODEL_API_KEY` | 模型服务密钥 |
| `MODEL_BASE_URL` | 接口地址 |
| `MODEL_NAME` | 模型名称 |

本地验收无需配置。三个变量都为空时不调用外部模型，决策来自本地规则，Trace 里的 `decision_source` 为 `local_policy`。

## 安装

在项目根目录执行。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS 或 Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

`pip install` 不会安装第三方包。需要在线模型时再编辑 `.env`。只做本地验收时保持 `.env.example` 的空值即可。

## 运行

在项目根目录、已激活虚拟环境后执行。

跑完全部本地场景，并把每条场景的输入、输出和 Trace 写入 `examples/<场景>/`：

```bash
python -m src.agent acceptance
```

单次规划。标准输出是任务计划、步骤状态、工具结果、费用合计，以及已保存方案或未完成原因。本地规则会把状态写到 `data/state/adhoc.json`，不覆盖 `examples/` 里的基线：

```bash
python -m src.agent run --theme "春季新品上新" --budget 10 --deadline 2026-11-20
```

按场景文件运行。结果写回该场景目录的 `output.json` 和 `trace.json`：

```bash
python -m src.agent run --input examples/normal/input.json
```

已配置三个模型变量时，由模型提议下一步，守卫仍决定能否保存。结果写入 `examples/model_runs/`，不覆盖基线。未配置时退出码为 2：

```bash
python -m src.agent run --decider model --theme "春季新品上新" --budget 10 --deadline 2026-11-20
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 评审入口

按这个顺序看：

1. 本文：环境、安装、运行。
2. [docs/01-requirements.md](docs/01-requirements.md)：用户、目标、范围和成功标准。
3. [docs/02-solution.md](docs/02-solution.md)：调用流程、动态决策和技术取舍。
4. [docs/03-evaluation.md](docs/03-evaluation.md)：测试预期、实际结果、失败和限制。文中引用 `examples/` 的对应文件。
5. [docs/04-ai-usage.md](docs/04-ai-usage.md)：AI 辅助内容、个人修改和验证。
6. [docs/05-retrospective.md](docs/05-retrospective.md)：最难问题、学习收获、下一步。
7. 执行 `python -m src.agent acceptance`，对照 `examples/` 里的输入、输出和 Trace。
8. 执行 `python -m unittest discover -s tests -v`。

## 目录

```text
README.md                  # 环境、安装、运行、评审入口
src/                       # 项目代码与模型/工具接入
tests/                     # 可执行测试
examples/                  # 输入、实际输出、Trace
data/                      # 合成资料和规则（按题目需要）
docs/
  01-requirements.md       # 用户、目标、范围和成功标准
  02-solution.md           # 调用流程、动态决策、技术取舍
  03-evaluation.md         # 测试预期、实际结果、失败和限制
  04-ai-usage.md           # AI 辅助内容、个人修改及验证
  05-retrospective.md      # 最难问题、学习收获、下一步
requirements.txt           # 依赖文件；本地验收无第三方包
.env.example               # 所需变量；本地验收无需配置
```

| 路径 | 放什么 |
| --- | --- |
| `src/` | 规划循环、四个工具、本地规则、可选模型客户端和守卫 |
| `tests/` | 可直接执行的验收测试，覆盖预算、依赖、失败后重规划和五条必须验收 |
| `examples/` | 每组实例的 `input.json`、`output.json`、`trace.json` |
| `data/` | 合成素材、方案费用、耗时和规则。运行时状态在 `data/state/`，不作为基线 |
| `docs/` | 需求、方案、评估、AI 使用和回顾 |

`PRD.md` 是实现前的规划说明，`TEST.md` 是预算、依赖和失败注入的核对记录。评审以 `docs/` 和 `examples/` 为准。
