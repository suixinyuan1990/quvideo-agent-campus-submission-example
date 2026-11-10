# 方案

## 代码与接入

| 路径 | 职责 |
| --- | --- |
| `src/scheduling_agent/agent.py` | 执行循环 |
| `src/scheduling_agent/model.py` | 本地观察决策，以及可选的远程模型适配器 |
| `src/scheduling_agent/tools.py` | 四个业务工具 |
| `src/scheduling_agent/store.py` | 草稿读写 |
| `src/scheduling_agent/report.py` | 把观察汇总成交付结果 |
| `src/scheduling_agent/catalog.py` | 读取 `data/` |
| `src/scheduling_agent/cli.py` | 命令行。可选读取仓库根目录的 `.env` |
| `src/scheduling_agent/types.py` | `Decision` 与 `Observation` |

默认模型是 `ObservationDecisionModel`。命令行 `--model llm` 时，同一步骤改由 `LLMDecisionModel` 请求兼容 OpenAI Chat Completions 的接口。远程调用只用标准库 `urllib`，需要 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。这三个变量都不填时，项目仍用本地模型，不访问网络。

## 调用流程

执行器在 `src/scheduling_agent/agent.py`。它不判断风险，也不判断时段是否冲突。每一轮只做这些事：

1. 若决策次数已经达到上限，停止并返回未完成。
2. 调用决策模型。模型只能看到用户请求和已经发生的工具观察。
3. 模型返回 `finish` 时，根据观察汇总交付结果。
4. 模型返回工具调用、但工具次数已经用完时，记录被拦住的动作，返回未完成，不执行该工具。
5. 否则执行工具，把参数、摘要和返回写入轨迹，回到第 1 步。

默认上限是 8 次决策、8 次工具调用。请求和环境变量可以改，命令行优先。

骨架工具只有四个：

| 工具 | 作用 |
| --- | --- |
| `read_material` | 读取素材。`refresh=true` 时合并 `data/supplements.json`。 |
| `check_rules` | 按禁用表述给出风险。故障时不返回“无风险”。 |
| `query_slots` | 查询要求时段，并给出同一天里更晚的空闲替代时段。 |
| `save_draft` | 写入或复用草稿。拒绝发布、拒绝未确认的改期、拒绝阻断级内容。 |

正常素材会走读取、规则、时段、保存。这只是资料齐全且没有风险时的结果，不是执行器写死的顺序。缺字段时第二次动作仍是读取；规则阻断时不会查询时段；时段占用且没有替代时段时不会保存。

## 动态决策

默认决策函数是 `ObservationDecisionModel.decide`。执行器每得到一次观察就重新调用它。函数里没有素材编号分支，下一步只看当前观察：

- 没有读取结果：读取素材。
- 字段缺失且还没补查：再次读取，依据里写明补查。
- 补查后仍缺失：结束并阻断。
- 规则工具返回 `retryable=true` 且只失败过一次：再查一次规则。
- 同一类错误不可重试，或补查后仍失败：结束。执行器本身不会因为异常再调一次工具。
- 规则阻断：结束，不排期。
- 时段可用：按原时段 `commit=true` 保存草稿。
- 时段占用、用户已确认一个空闲时段：按确认结果 `commit=true`。
- 时段占用、用户未确认、存在替代时段：`commit=false` 保存建议，标记待确认。
- 没有替代时段，或用户确认的时段不可用：结束并等待确认，不另选一个时间写进去。
- 保存返回成功、重复或失败：结束。失败不会被说成成功。

两条已经提交的分叉：

1. 时段结果不同。M10 的查询摘要是“10:00 可用”，下一步 `save_draft` 且 `commit=true`，见 `examples/01-normal/trace.json` 第 3 步的 `next_arguments`。M01 的查询摘要是“18:00 已被占用（SCH-1800），可用替代时段 19:00”，下一步仍是 `save_draft`，但 `commit=false`、`suggested_slot=19:00`，见 `examples/04-slot-conflict/trace.json`。
2. 规则工具结果不同。M11 两次都返回超时，第二次的决策依据是“决定补查一次”，补查失败后结束，见 `examples/07-tool-failure/trace.json`。M12 第一次同样超时且可补查，第二次检查通过，模型接着查询 13:00 并保存草稿，见 `examples/11-transient-then-schedule/trace.json`。

`tests/test_decisions.py` 还直接把两组观察交给同一个函数：只改时段观察，保存参数就从承诺 18:00 变成待确认的 19:00；只把规则错误从可重试改成不可重试，第二次规则调用就消失。

远程模型适配器 `LLMDecisionModel` 使用同一 `Decision` 结构，通过标准库请求 `/chat/completions`。输出无法解析时，循环记为未完成，不会自动再问一次。验收轨迹没有走这条路径。

## 技术取舍

结果汇总放在 `report.py`，不让模型的结束语决定保存状态。`draft_save_status=saved` 必须对应一次 `created=true` 的保存观察，`failed` 必须对应失败观察，`duplicate` 必须对应重复观察。发布状态在汇总时固定为 `not_published`。

用户确认放在请求里，并由 `Toolset` 单独持有。保存工具忽略模型另外声称的 `confirmed_slot`。两边不一致时返回 `confirmation_mismatch`；未确认就承诺新时间时返回 `hard_requirement_locked` 或 `confirmation_required`。

草稿身份是素材内容、日期、要求时段、建议时段、是否承诺和用户确认值的哈希，取前 12 位并加上 `D-`。M01 的待确认草稿因此稳定为 `D-55e1dafed554`。确认 19:00 会得到另一份草稿，因为请求已经不同；各自重复提交仍然只保留一份。新草稿成功写入后，同一素材、同一内容版本、同一日期和要求时段上仍待确认的旧草稿改为 `superseded`。这一步只改确认状态，不改写硬性发布时间，也不把草稿标成已发布。保存失败或重复保存不会接替旧草稿。

故障写在 `data/tool_faults.json`，不写在决策函数里。M04 的保存失败不可重试。M11 的规则超时可重试且失败次数为 2。M12 的同类超时只失败 1 次。这样同一套决策代码会走出阻断和继续两条路。

没有引入 Agent 框架。提交需要的是可检查的循环、参数、返回摘要和后续动作，标准库足够表达，也避免框架把决策藏进预置图。

默认使用可复现的观察决策，而不是在评分环境里调用远程模型。代价是决策规则能被直接读到。收益是示例和测试不依赖密钥，换一次工具结果就能稳定复现动作变化。
