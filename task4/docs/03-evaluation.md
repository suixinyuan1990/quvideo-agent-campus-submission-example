# 评测

需求见 [01-requirements.md](01-requirements.md)。测量命令是 `python -m pytest`。每道验收题的输入、结果和 Trace 在 `examples/scenarios/`。参考实例的命令行输出在 `examples/last-run.json`。审核原始记录在 `examples/audit/report.json`，叙述版在 [TEST.md](../TEST.md)。

最近一次实测：Python 3.12.8，pytest 9.2.0，`tests/` 共 14 项，14 通过，0 失败，用时 2.63 秒。审核得分 100/100，关键缺陷为空。命令行主题「详细介绍支持字幕」、目标 30 秒，状态 `completed`，预计总时长 28.0 秒，来源 ID 为 P01。

## 1. 预期

| 场景 | 预期 |
| --- | --- |
| 正常生成 | 状态 `completed`。七项交付齐全。来源 ID 来自本轮检索。预计总时长不超过目标时长。阻断规则通过。素材没有的数字不出现。 |
| 缺关键信息 | 状态 `needs_input`，指出缺少的字段。Trace 中没有检索。 |
| 无素材 | 检索为空后改写查询或请求补充。最终状态为 `no_material` 或 `needs_input`。来源 ID 为空。 |
| 工具失败 | 失败的工具自动重试一次。仍失败则状态 `tool_failure`，并写明工具名。与检索为空区分开。 |
| 超时长后的修正 | 先出现一次超时估算，缩短后再估算通过，状态 `completed`。Trace 保留修改前和修改后的结果。 |
| 超时长后的明确失败 | 时长与必须保留的阻断规则不能同时满足。状态 `unsatisfied`，附草稿和最后一次估算秒数。 |

高分依据是有效修正和事实可追溯。完成稿里出现素材正文没有的产品事实，记为关键缺陷。出现关键缺陷时，事实可追溯记 0 分。

## 2. 实际结果

剧本模型、夹具语料 `data/fixtures/materials.jsonl`。样例文件与下表一一对应。

| 场景 | 样例 | 状态 | 实际结果 | 动作 |
| --- | --- | --- | --- | --- |
| 正常生成 | `examples/scenarios/normal.json` | `completed` | 引用 P01，旁白「这个功能支持字幕」，估算 2.000 秒，风险写明短于 30 秒 | `search` → `draft` → `estimate` → `check_rules` → `finish` |
| 缺少主题 | `examples/scenarios/missing-theme.json` | `needs_input` | 指出缺少主题 | `ask` |
| 缺少目标时长 | `examples/scenarios/missing-duration.json` | `needs_input` | 指出缺少目标时长 | `ask` |
| 主题只有「做一个视频」 | `examples/scenarios/vague-theme.json` | `needs_input` | 说明主题无法形成检索查询 | `ask` |
| 无素材 | `examples/scenarios/no-material.json` | `no_material` | 查询「运动鞋气垫」和「运动鞋」都为空，来源 ID 为空 | `search` → `search` → `finish` |
| 检索失败 | `examples/scenarios/tool-failure-search.json` | `tool_failure` | 素材检索连续失败两次，来源 ID 为空 | `search` → `search` |
| 估算失败 | `examples/scenarios/tool-failure-estimate.json` | `tool_failure` | 已检索到 P01，时长估算连续失败两次 | `search` → `draft` → `estimate` → `estimate` |
| 规则检查失败 | `examples/scenarios/tool-failure-check.json` | `tool_failure` | 估算已得到 2.000 秒，规则检查连续失败两次 | `search` → `draft` → `estimate` → `check_rules` → `check_rules` |
| 超时长后修正 | `examples/scenarios/over-duration-revised.json` | `completed` | 先 38000 毫秒，再 28000 毫秒。终稿 28.0 秒，引用 P01 | `search` → `draft` → `estimate` → `check_rules` → `draft` → `estimate` → `check_rules` → `finish` |
| 超时长后失败 | `examples/scenarios/over-duration-unsatisfied.json` | `unsatisfied` | 声明本身 5.250 秒，目标 4 秒，最后一次估算 6.250 秒，草稿仍引用 P01 | `search` → `draft` → `estimate` → `check_rules` → `finish` |
| 无效果数据 | `examples/scenarios/number-claim.json` | `completed` | 第一稿的「效率提升 80%」被 `FACT-NUMBER` 拒绝，终稿只保留「支持字幕」 | `search` → `draft` → `estimate` → `check_rules` → `draft` → `estimate` → `check_rules` → `finish` |

`AG-dev-000533` 的正文没有「100%」。用这句正文检查「100%高支棉」时，规则 ID 为 `FACT-NUMBER`。载入 `reference_summaries.jsonl` 会直接拒绝。

### 来源、时长和检查的对应

对照使用同一份 Trace 里的检索命中、最后一次成功估算和最后一次成功规则检查。分镜来源 ID 来自这次检索，汇总来源 ID 与各镜来源 ID 相同。每个镜头的 `duration_sec` 等于该镜最后一次估算，总时长等于这次估算的 `total_sec`。状态为 `completed` 时，最近一次规则检查必须通过，且估算毫秒数不超过目标时长。

| 运行 | 状态 | 来源 ID | 分镜时长 | 总时长 | 与检查的关系 |
| --- | --- | --- | --- | --- | --- |
| 详细介绍，目标 30 秒 | `completed` | P01 | 28.0 | 28.0 | 最后一次检查通过，28 秒不超过 30 秒 |
| 详细介绍，目标 40 秒 | `completed` | P01 | 与估算一致 | 38.0 | 最后一次检查通过，38 秒不超过 40 秒 |
| 详细介绍，目标 20 秒 | `completed` | P01 | 2.0 | 2.0 | 112 字的 28 秒仍超时，再压到「这个功能支持字幕」后通过 |
| 详细介绍，目标 1 秒 | `unsatisfied` | P01 | 2.0 | 2.0 | 最短事实句已是 2 秒，仍超过 1 秒 |
| 普通介绍 | `completed` | P01 | 与估算一致 | 2.0 | 检查通过，标题「支持字幕」在 P01 正文里 |
| 带有效果数据的介绍 | `completed` | P01 | 与估算一致 | 2.0 | 终稿检查通过；第一稿的 80% 没有留到完成稿 |
| 必须保留声明，目标 4 秒 | `unsatisfied` | P01 | 与估算一致 | 6.250 | 来源和时长仍对得上，状态不是 `completed` |
| 运动鞋气垫 | `no_material` | 空 | 无分镜 | 无估算 | 两次检索都是空列表 |
| P01 改成食堂菜单 | `no_material` | 空 | 无分镜 | 无估算 | 检索结果里没有 P01，交付也不引用它 |
| P01 改为字幕翻译 | `completed` | P01 | 与估算一致 | 短于 30 秒 | 标题「字幕翻译」在新正文里 |

这 10 次运行的对应问题列表都是空的。连接语不记为产品事实。记为产品事实的是标题、百分数、「倍」和「效率提升」。

### 改变时长或检索结果

主题同为「详细介绍支持字幕」，只改目标时长。第一次规则检查之后的动作如下。

| 目标时长 | 第一次检查后的动作 | 最终状态 | 总时长 |
| --- | --- | --- | --- |
| 30 秒 | `draft` | `completed` | 28.0 |
| 40 秒 | `finish` | `completed` | 38.0 |
| 20 秒 | `draft` | `completed` | 2.0 |
| 1 秒 | `draft` | `unsatisfied` | 2.0 |

30 秒时，152 字估成 38 秒，下一步压到 112 字。40 秒时，38 秒已经不超过目标，下一步直接完成。20 秒时，112 字的 28 秒仍超时，再改成 8 字事实句后完成。1 秒时，这句最短事实句仍是 2.0 秒，状态为 `unsatisfied`。四档来源都是 P01。

只在内存里替换 P01，不改 `data/fixtures/materials.jsonl`。

| 检索正文 | 第一次检索后的动作 | 最终结果 |
| --- | --- | --- |
| 原正文「功能#支持字幕」 | `draft` | `completed`，标题「支持字幕」 |
| 改成食堂菜单 | `search` | `no_material`，来源 ID 为空 |
| 改成「功能#字幕翻译」 | `draft` | `completed`，标题「字幕翻译」，旁白「这个功能字幕翻译」 |

主题「介绍支持字幕的效果」的第一稿写了「效率提升 80%」。第一次规则检查未通过，违规规则是 `FACT-NUMBER`，且只出现一次。终稿旁白是「这个功能支持字幕」，状态 `completed`，来源仍是 P01。

### 审核分数

| 项目 | 满分 | 得分 | 结果 |
| --- | --- | --- | --- |
| 事实可追溯 | 50 | 50 | 10 次运行的来源、分镜时长、总时长和状态都与 Trace 一致。完成稿的标题和数字都能在被引正文里找到。 |
| 有效修正 | 50 | 50 | 目标改为 40 秒、20 秒或 1 秒后，下一步动作改变。正文改掉或改名后，检索或引用跟着变。「效率提升 80%」在完成前被删掉。 |
| 合计 | 100 | 100 | 无关键缺陷。 |

事实可追溯的 50 分里，30 分看逐条对应，20 分看完成稿没有超出正文的标题、百分数或「效率提升」。有效修正的 50 分里，目标放宽到 40 秒记 10 分，目标收到 20 秒和 1 秒记 10 分，正文改成无关内容 15 分，正文改名 10 分，删掉 80% 为 5 分。

## 3. 曾经偏离、现已改过的行为

这些是同一套标准下看过的偏差，当前代码已经按实测结果运行：

1. 目标 20 秒时，112 字稿估成 28 秒后，下一步仍提交同一份 112 字稿，然后停在 `unsatisfied`。现在 112 字仍超时会改成「这个功能支持字幕」，20 秒目标以 2.0 秒完成。1 秒目标停在这句最短事实句，状态 `unsatisfied`。
2. 口播稿的字幕复制旁白时，「效率提升 80%」会报出两条 `FACT-NUMBER`。现在相同正文只查一次。
3. 改写后的查询若和上一次相同，仍会再检索一次。现在直接 `no_material`。

## 4. 失败与限制

这 14 项没有失败。

已知边界：

- 五类验收跑的是剧本模型和 P01 夹具，不是对 115669 条 AdvertiseGen 逐条生成。
- 真实模型的客户端已经接上，这轮没有用密钥做端到端调用。
- 品牌规则只有验收用的那一条固定声明。开放素材库没有配套规则集。
- 只有一条素材时，BM25 分数可能为负。是否命中由二元组重叠和属性值包含决定，BM25 只负责排序。
- 短于目标时长可以 `completed`，风险写「短于目标时长」。最短事实句仍超过目标时，状态是 `unsatisfied`。
