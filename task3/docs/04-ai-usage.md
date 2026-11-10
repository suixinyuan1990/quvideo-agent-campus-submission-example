# AI 使用记录

本项目的需求整理、方案、代码、测试和文档，是在 Cursor 里由人指定范围、由 AI 起草并反复修改完成的。下面区分 AI 起草的内容、由人改过方向的决定，以及实际跑过的验证。没有把未发生的手工改稿写成个人修改。

## 1. AI 起草了什么

- [README.md](../README.md) 的运行说明和最初的需求正文。需求正文现已移到 [01-requirements.md](01-requirements.md)。
- [PRD.md](../PRD.md) 的技术栈、模块边界和检索设计。
- `src/knowledge_agent/` 的语料、工具、剧本模型、循环、校验、命令行和评测。
- `tests/test_agent.py`、`tests/test_audit.py`，以及 `examples/` 里由测试写出的输入、输出和 Trace。
- FaithEval inconsistent v1.0 的引入说明、`data/faitheval-inconsistent/prepare.py`，以及文档拆分。
- [TEST.md](../TEST.md) 和本目录下的五份说明。

AI 选择并实现的默认路径是：Python 3.12、自写循环、内存 JSONL、BM25 加短语加字符 3-gram、倒数排名融合、剧本模型。这些选择写在 [02-solution.md](02-solution.md)。

## 2. 人改过的方向

这些决定改变了 AI 的初稿，并留在当前代码里：

| 决定 | 结果 |
| --- | --- |
| 先把优化后的需求写入 README，暂不开发 | 代码在需求、目录和资料定下来之后才写。 |
| 评审目录按 README、`src/`、`tests/`、`examples/`、`data/`、`docs/` 安排 | 目录按这个结构落地。`docs/` 在实现和测试之后补齐。 |
| 找一份符合「两份文档冲突、又没有范围和优先级」的开源数据 | 采用 Salesforce/FaithEval-inconsistent-v1.0。不把段落改写成报销制度，也不重新许可原文。 |
| 第一版不要向量数据库，也不要 Agent 框架 | 检索停留在内存词法三路。LangChain、LlamaIndex 未引入。 |
| 要多重检索，并提高相关文档的精度 | 一次 `search` 内做三路召回和融合，接近分数的冲突文档必须留下。 |
| 资料没有所问事实时明确拒绝 | 中文问句增加事实覆盖和适用范围检查。发票、结转、预约会议室、试用期工资改为拒绝。 |
| 按「引用必须支持回答、替换文档后答案要变」审计，无依据回答算关键缺陷 | 第一次审计 75 分。两处缺陷修复后重测为 100 分。 |

人没有单独改过某一行实现。上面每一条都是对话里的范围约束，随后由 AI 改代码和测试来满足。

## 3. 验证

验证都在本机用剧本模型完成，没有调用付费模型接口。

| 检查 | 命令或位置 | 结果 |
| --- | --- | --- |
| 全套测试 | `python -m pytest` | 10 通过，0 失败，0.67 秒 |
| 六类场景和拒绝 | `tests/test_agent.py`，样例在 `examples/scenarios/` | 通过 |
| 引用与替换审计 | `tests/test_audit.py`，记录在 `examples/audit/report.json` | 100/100，关键缺陷为空 |
| FaithEval 抽样 | 种子 `20260310`，各 20 题，`examples/faitheval-sample/summary.json` | 40/40 |
| 报销冲突样例 | `python -m knowledge_agent.cli --question "报销期限多久？" --corpus data/policies` | `examples/last-run.json` 为冲突，引用 30 天和 15 天 |

修复过程中跑过失败的中间结果，没有当作最终结论。包括：试用期小数被切成 `0.`、FaithEval 25/40、事实拒绝过严导致年假题被拒、以及「开头句子相同就取消冲突」导致抽样掉到 39/40。这些都在再次通过测试后才写入 [03-evaluation.md](03-evaluation.md)。

真实模型路径只检查了系统提示是否写上同一套拒绝和冲突规则，没有用 API 密钥做端到端调用。
