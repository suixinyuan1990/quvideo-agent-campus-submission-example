# 资料

这里放合成资料，以及题目需要的冲突资料和作答规则。制度验收与 FaithEval 不放在同一次检索里。

## 合成制度

`data/policies/documents.jsonl` 是合成的 FAQ 和制度，不代表真实公司规定。

| 文档 ID | 版本日期 | 规则 |
| --- | --- | --- |
| `POL-LEAVE-001` | 2024-03-01 | 入职满一年每年 10 天带薪年假。试用期员工不适用本条。 |
| `POL-LEAVE-PROB` | 2024-03-01 | 试用期年假每满一个月 0.5 天。只适用于试用期员工。 |
| `POL-EXP-D01` | 2023-06-01 | 报销期限 30 天。没有适用范围，没有优先级。 |
| `POL-EXP-D02` | 2024-01-15 | 报销期限 15 天。没有适用范围，没有优先级。 |
| `POL-MEET-001` | 2025-02-01 | 远程协作工具单次会议最长 90 分钟。没有写如何预约会议室。 |

问「报销期限多久」且两份报销制度都检索到时，列出冲突和两边引用，并请求确认适用哪份制度，不能擅自回答 15 天。版本日期只说明 D02 更晚，不能单独作为采用依据。只检索到其中一份、且没有第二份冲突文档时，按该份回答。原文没有所问事实，或文档写明的适用范围对不上时，拒绝回答。

## 冲突数据集

另外引入 [FaithEval inconsistent v1.0](https://huggingface.co/datasets/Salesforce/FaithEval-inconsistent-v1.0)，用来在更多题上验收同一条冲突规则。

## 和报销期限例子的对应关系

参考规则是：D01 写明报销期限 30 天，D02 写明 15 天，两份都没有适用范围和优先级。问「报销期限多久」时，要列出冲突和引用，并请求确认适用哪份制度；不能擅自回答 15 天。只检索到 D01、且没有第二份冲突文档时，按 D01 回答。

FaithEval 的 inconsistent 子集是同一结构。每题原文里有两段，都以 `Document:` 开头，分别支持两个不同答案。数据集没有给出适用范围、优先级或版本日期。官方评测约定：上下文存在冲突或多个答案时，回答应为 conflict，而不是两个答案里的一个。代码与说明见 [SalesforceAIResearch/FaithEval](https://github.com/SalesforceAIResearch/FaithEval)。

用第一题代替上面的 30 天 / 15 天：

| 角色 | 文档 ID | 原文 | 该文档支持的答案 |
| --- | --- | --- | --- |
| D01 | `FE-55ec33bd05b84c6c82c42743d70e219d-D01` | Sky picked up the remaining four for £1.3bn. | Sky |
| D02 | `FE-55ec33bd05b84c6c82c42743d70e219d-D02` | Hulu picked up the remaining four for £1.3bn. | Hulu |

问题是 “Who purhcased the remaining 4 pacakages available to broadcasters?”。两份文档都在检索结果里时，任务 `55ec33bd05b84c6c82c42743d70e219d-conflict` 要求：

- 同时引用 D01 和 D02 的原文
- 说明 Sky 与 Hulu 冲突
- 请求确认适用哪一份文档
- 不能把 Sky 或 Hulu 单独当作唯一答案

只检索到 D01 时，任务 `55ec33bd05b84c6c82c42743d70e219d-only-d01` 要求依据 D01 回答 Sky，并引用该文档。这时没有第二份文档，不构成冲突。

## 文件

```text
data/faitheval-inconsistent/
  test-00000-of-00001.parquet  # 原始测试集，1500 行
  prepare.py                   # 把每行拆成 D01 / D02，并生成任务
  documents.jsonl              # 3000 份文档
  tasks.jsonl                  # 1500 道冲突题 + 1500 道只检索到 D01 的题
  manifest.json                # 行数与原始文件校验值
```

原始文件 SHA-256：`a4fd32a58c28267bc3b217a6006af68d95f354568f42702ba18d9b8c76fffa15`。

重新生成拆分结果：

```text
python data/faitheval-inconsistent/prepare.py
```

这只改写 `documents.jsonl`、`tasks.jsonl` 和 `manifest.json`，不下载数据，也不运行问答。

## 文档与任务字段

每份文档包含：

| 字段 | 含义 |
| --- | --- |
| `doc_id` | `FE-{qid}-D01` 或 `FE-{qid}-D02`。 |
| `version_date` | 空。原数据没有版本日期，不能用来选择 D01 或 D02。 |
| `doc_type` | `passage`。这些是问答段落，不是公司制度原文。 |
| `scope` / `priority` | 空。没有适用范围，也没有效力优先级。 |
| `body` | 去掉 `Document:` 前缀后的原文，引用必须来自这里。 |
| `supported_answer` | 该文档支持的答案。 |
| `answer_in_body` | 答案字符串能否在正文中按不区分大小写的方式直接找到。 |

冲突任务 `scenario = document_conflict` 使用两份文档，`expected_status` 为 `conflict`。`forbidden_sole_answers` 里的两个答案都不能单独作为结论。`must_request_applicable_document` 为 true。

单文档任务 `scenario = single_document` 只放入 D01，`derived` 为 true。这是按本项目规则从同一题拆出来的视图，FaithEval 原文件没有单独发布这个切分。`expected_status` 为 `answered`，`expected_answer` 是 D01 的 `supported_answer`。

## 使用时的限制

- 1500 行全部能拆成两份文档，且两个答案都不同。其中 207 份文档的 `supported_answer` 不是正文里的连续原文，常见原因是换行、连字符或答案比原句多了几个词。引用仍必须摘正文，不能把对不齐的答案字符串写成原文片段。
- 段落主题来自 SQuAD、NewsQA、TriviaQA 等公开问答集，覆盖体育、医学、百科等，不是报销制度。它检验的是冲突时不选边、单文档时按该文档作答。
- 原发布说明这份数据用于论文研究。上游段落改写自 SQuAD、NewsQA、TriviaQA、SearchQA、HotpotQA、Natural Questions、BioASQ、TextbookQA、RACE、DROP。SQuAD 为 CC BY-SA 4.0，其余来源保留各自条款。本仓库不把这些正文再许可成项目自己的许可证。FaithEval 代码仓库为 Apache-2.0。
- 论文：Yifei Ming 等，FaithEval: Can Your Language Model Stay Faithful to Context, Even If "The Moon is Made of Marshmallows"，arXiv:2410.03727。
