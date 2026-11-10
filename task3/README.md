# 企业知识问答 Agent

帮助员工依据企业内部制度与产品资料，得到可回溯、可核验的答案。本文只做环境、安装、运行和评审入口。

## 评审入口

1. 本文：环境、安装、运行、配置。
2. [docs/01-requirements.md](docs/01-requirements.md)：用户、目标、范围和成功标准。
3. [docs/02-solution.md](docs/02-solution.md)：调用流程、动态决策和技术取舍。
4. [docs/03-evaluation.md](docs/03-evaluation.md)：测试预期、实际结果、失败和限制。
5. `examples/`：每道验收题的输入、实际输出和 Trace。
6. [docs/04-ai-usage.md](docs/04-ai-usage.md)：AI 辅助内容、个人修改及验证。
7. [docs/05-retrospective.md](docs/05-retrospective.md)：最难问题、学习收获、下一步。

必须通过的六类场景是：明确答案、文档冲突、资料外问题、改写后的相似问题、上下文追问、工具失败。场景定义见 [docs/01-requirements.md](docs/01-requirements.md)。合成资料和冲突规则见 [data/README.md](data/README.md)。

## 项目结构

```text
README.md              # 环境、安装、运行、评审入口
src/                   # 项目代码与模型/工具接入
tests/                 # 可执行测试
examples/              # 输入、实际输出、Trace
data/                  # 合成资料和规则（按题目需要）
docs/
  01-requirements.md   # 用户、目标、范围和成功标准
  02-solution.md       # 调用流程、动态决策、技术取舍
  03-evaluation.md     # 测试预期、实际结果、失败和限制
  04-ai-usage.md       # AI 辅助内容、个人修改及验证
  05-retrospective.md  # 最难问题、学习收获、下一步
requirements.txt       # Python 依赖
.env.example           # 所需变量；剧本模型无需配置
```

| 路径 | 放什么 |
| --- | --- |
| `src/` | Agent 循环、模型接入、文档检索与片段读取。 |
| `tests/` | 可重复执行的验收测试。 |
| `examples/` | 与测试对应的输入、程序实际输出、工具调用 Trace。 |
| `data/` | 合成制度，以及题目所需的冲突资料和作答规则。 |
| `docs/` | 需求、方案、评测、AI 使用记录和复盘。不放可执行代码。 |

## 环境

- 运行时是 Python 3.12。
- 剧本模型运行和测试不需要密钥。真实调用模型时才使用 `MODEL_BASE_URL`、`MODEL_API_KEY` 和 `MODEL_NAME`，变量名见 `.env.example`。

## 安装

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

运行期依赖为 `pydantic`、`openai`、`rank-bm25` 和 `pytest`。

## 运行

```powershell
python -m knowledge_agent.cli --question "报销期限多久？" --corpus data/policies
python -m pytest
python -m knowledge_agent.evaluate --tasks data/faitheval-inconsistent/tasks.jsonl
```

默认使用剧本模型，不访问网络。`--model openai` 才读取 `.env`。问答结果和 Trace 写入 `examples/last-run.json`。六类场景的样例在 `examples/scenarios/`。FaithEval 抽样结果在 `examples/faitheval-sample/summary.json`，抽样种子是 `20260310`，冲突题和单文档题各 20 道。

## 配置

剧本模型无需配置。

真实模型把 `.env.example` 复制为 `.env` 后填写三个变量。`.env` 不要提交。
