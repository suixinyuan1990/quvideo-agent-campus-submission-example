# 素材审核与发布排期 Agent

内容团队给出一条待处理素材后，这个程序读取素材、核对审核规则、查询发布时间，并只保存排期草稿。它不会发布。模型每看到一次工具结果，就重新决定下一步：补查、建议替代时段、请求确认、阻断，或结束。

## 环境

- Python 3.10 及以上。本仓库在 Python 3.12.8 上跑通测试。
- 运行时代码只使用标准库。
- 测试依赖 pytest。当前验证使用 pytest 9.2.0。
- 不需要 API 密钥。不创建 `.env` 也可以运行全部示例和测试。变量说明在 [.env.example](.env.example)，其中写明本地运行无需配置。
- 在仓库根目录执行下面的命令。Windows 示例使用 PowerShell。

## 安装

```powershell
python -m pip install -r requirements.txt
```

依赖文件是 [requirements.txt](requirements.txt)，里面只有测试用的 pytest。运行时代码使用 Python 标准库，没有 `package.json`，也没有业务侧第三方包。

## 运行

PowerShell 先把 `src` 放到模块路径：

```powershell
$env:PYTHONPATH = "src"
python -m scheduling_agent examples/04-slot-conflict/input.json --store var/m01.json
```

常用参数：

- `--store`：草稿文件。默认是 `var/drafts.json`，会保留上次结果。评审单次结果时换一个新文件。
- `--trace`：把运行记录写到文件。
- `--output`：把交付结果写到文件，不再打印到终端。
- `--max-steps`、`--max-tool-calls`：覆盖默认上限 8 和 8。请求 JSON 里的同名字段也会生效，命令行优先。
- `--model local`：默认。离线观察决策，示例都由它生成。
- `--model llm`：调用兼容 OpenAI Chat Completions 的接口。需要 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。

退出码：`0` 表示决策已经结束；`2` 表示达到步数或工具次数上限，任务未完成；`3` 表示草稿保存失败；`1` 表示输入或模型配置不可用。保存失败仍然会在 JSON 里写明 `draft_save_status=failed`，不会被算成保存成功。

重新生成本仓库已提交的示例：

```powershell
$env:PYTHONPATH = "src"
python -m scheduling_agent.build_examples
python -m pytest -q
```

## 评审入口

建议按这个顺序看：

1. 本文「题目要求」和「验收对照」，以及 [docs/01-requirements.md](docs/01-requirements.md)：用户、目标、范围和成功标准。
2. [docs/02-solution.md](docs/02-solution.md)：调用流程、动态决策和技术取舍。
3. [docs/03-evaluation.md](docs/03-evaluation.md)：每条验收对应哪个文件，以及实际跑出来的字段。
4. 轨迹对照：
   - [examples/01-normal/trace.json](examples/01-normal/trace.json)：时段可用，按原时间保存草稿。
   - [examples/04-slot-conflict/trace.json](examples/04-slot-conflict/trace.json)：同一类查询发现 18:00 被占用后，改成建议 19:00 并 `commit=false`。
   - [examples/07-tool-failure/trace.json](examples/07-tool-failure/trace.json)：规则工具连续失败后阻断。
   - [examples/11-transient-then-schedule/trace.json](examples/11-transient-then-schedule/trace.json)：第一次失败可补查，补查成功后才继续排期。
5. [docs/04-ai-usage.md](docs/04-ai-usage.md) 和 [docs/05-retrospective.md](docs/05-retrospective.md)：哪些内容由助手生成，以及确认边界后来改了什么。
6. 运行 `python -m pytest -q`。当前结果是 38 项通过。详见 [docs/03-evaluation.md](docs/03-evaluation.md)。

人工复核冲突时，可以把 `data/slots.json` 里 2026-11-12 的 `18:00` 改成空闲，再用一个新的 `--store` 重跑 M01。程序会回到用户要求的 18:00，而不是继续建议 19:00。改完共享数据后需要重新执行 `build_examples`，否则示例一致性测试会失败。

## 题目要求

### 用户与目标

帮助内容团队找出待处理素材，形成无冲突、可确认的发布排期。

### 输入与材料

素材 ID、元数据、发布时间要求、已有排期与审核规则。程序提供四个工具：素材读取、规则检查、时段查询、排期草稿保存。

### 交付结果

每项素材返回审核状态、风险原因、建议时段、待确认项、草稿保存状态。只保存草稿，不接真实发布。

### 动态决策

模型根据风险或时段冲突，选择补查、替代时段、请求确认或阻断。未经用户同意，不得擅自改变硬性发布要求。

这里的“模型步骤”由执行循环反复调用。默认实现读取当前工具观察后选择下一动作；配置 `--model llm` 时，同一步骤改由远程模型输出动作。提交的示例全部来自默认实现，便于复核。

### 必须验收

- 正常排期
- 素材信息缺失
- 规则风险
- 时段冲突
- 重复提交
- 保存失败

另外，项目要求至少两条执行路径证明模型会因工具结果改变动作，并且达到步数或工具调用上限时返回明确的未完成状态。信息不足和工具失败也各有记录。

### 参考实例

素材 M01 无风险，用户要求 18:00，但该时段已占用，19:00 可用。模型建议 19:00 并标记待确认，不得称为已发布。相同请求重复保存只产生一份草稿。保存失败须明确返回失败。

对应结果：

- [examples/04-slot-conflict/output.json](examples/04-slot-conflict/output.json)：`suggested_slot` 为 `19:00`，`committed_slot` 为 `null`，`confirmation_status` 为 `pending`，`publish_state` 为 `not_published`。
- [examples/05-duplicate-submit/output.json](examples/05-duplicate-submit/output.json)：两次运行得到同一个草稿 `D-55e1dafed554`，第二次是 `duplicate`，存储里只有 1 份。
- [examples/06-save-failure/output.json](examples/06-save-failure/output.json)：`draft_save_status` 为 `failed`，`save_error` 为 `storage_unavailable`。

用户若在请求中给出 `"confirmed_slot": "19:00"`，同一条 M01 会改写硬性时间并保存已确认草稿，状态仍然是未发布。见 [examples/10-confirmed-alternative/output.json](examples/10-confirmed-alternative/output.json)。

### 审核要点

核对风险、冲突、确认状态与保存结果。更换占用时段后再提交，应回到新的工具结果，而不是沿用旧建议。高分依据是冲突调整、确认边界与防重复。越权发布或虚报保存成功属于关键缺陷。

程序里的对应约束：

- 没有发布工具。保存接口收到 `publish=true` 时返回 `publish_forbidden`，并且不写草稿。
- 交付文案和草稿记录的发布状态固定为未发布。结果汇总如果缺少成功的保存观察，就不能把状态写成 `saved`。
- 用户是否同意改期，以请求里的 `confirmed_slot` 为准。模型参数里自行填写的确认时段不会被采纳。
- 相同的素材内容、要求时段、建议时段和确认状态再次保存时，返回已有草稿，不新增第二份。
- 新草稿成功写入后，同一素材版本上仍待确认的旧草稿改为 `superseded`。这一步不改写硬性发布时间。保存失败不会接替旧草稿。示例 10 使用空草稿库，因此文件里只有新确认草稿；同一库上的接替由 `tests/test_decisions.py` 覆盖。

## 验收对照

| 验收点 | 输入 | 实际结果位置 |
| --- | --- | --- |
| 正常排期 | [examples/01-normal/input.json](examples/01-normal/input.json) | [output](examples/01-normal/output.json)、[trace](examples/01-normal/trace.json) |
| 素材信息缺失 | [examples/02-missing-info/input.json](examples/02-missing-info/input.json) | [output](examples/02-missing-info/output.json)、[trace](examples/02-missing-info/trace.json) |
| 规则风险 | [examples/03-rule-risk/input.json](examples/03-rule-risk/input.json) | [output](examples/03-rule-risk/output.json)、[trace](examples/03-rule-risk/trace.json) |
| 时段冲突 | [examples/04-slot-conflict/input.json](examples/04-slot-conflict/input.json) | [output](examples/04-slot-conflict/output.json)、[trace](examples/04-slot-conflict/trace.json) |
| 重复提交 | [examples/05-duplicate-submit/input.json](examples/05-duplicate-submit/input.json) | [output](examples/05-duplicate-submit/output.json)、[trace](examples/05-duplicate-submit/trace.json) |
| 保存失败 | [examples/06-save-failure/input.json](examples/06-save-failure/input.json) | [output](examples/06-save-failure/output.json)、[trace](examples/06-save-failure/trace.json) |
| 工具失败 | [examples/07-tool-failure/input.json](examples/07-tool-failure/input.json) | [output](examples/07-tool-failure/output.json)、[trace](examples/07-tool-failure/trace.json) |
| 执行步数上限 | [examples/08-step-limit/input.json](examples/08-step-limit/input.json) | [output](examples/08-step-limit/output.json)、[trace](examples/08-step-limit/trace.json) |
| 工具次数上限 | [examples/09-tool-call-limit/input.json](examples/09-tool-call-limit/input.json) | [output](examples/09-tool-call-limit/output.json)、[trace](examples/09-tool-call-limit/trace.json) |
| 用户确认后改期 | [examples/10-confirmed-alternative/input.json](examples/10-confirmed-alternative/input.json) | [output](examples/10-confirmed-alternative/output.json)、[trace](examples/10-confirmed-alternative/trace.json) |
| 补查成功后继续 | [examples/11-transient-then-schedule/input.json](examples/11-transient-then-schedule/input.json) | [output](examples/11-transient-then-schedule/output.json)、[trace](examples/11-transient-then-schedule/trace.json) |

`examples/05` 的输出是两次运行的包装：`store_draft_count`、`drafts` 和 `runs`。其余示例的输出就是单次交付结果。

## 目录

```
README.md                 环境、安装、运行、评审入口
requirements.txt          依赖文件。只声明 pytest，运行时无第三方包
.env.example              环境变量说明。本地运行无需创建 .env
pyproject.toml            包元数据。安装测试依赖不是运行示例的前提
src/scheduling_agent/     项目代码，以及本地模型与可选远程模型的接入
tests/                    可执行测试
examples/                 每个场景一份 input.json、output.json、trace.json
data/                     按题目准备的合成素材、规则、时段、故障和补查资料
docs/01-requirements.md   用户、目标、范围和成功标准
docs/02-solution.md       调用流程、动态决策、技术取舍
docs/03-evaluation.md     测试预期、实际结果、失败和限制
docs/04-ai-usage.md       AI 辅助内容、后续修改及验证
docs/05-retrospective.md  最难问题、学习收获、下一步
var/                      本地草稿目录。json 默认不提交
```

`src/scheduling_agent` 里的接入点：

| 文件 | 作用 |
| --- | --- |
| `agent.py` | 执行循环。只负责请模型决策、调用工具、记录观察 |
| `model.py` | 默认的 `ObservationDecisionModel`；`--model llm` 时换成 `LLMDecisionModel` |
| `tools.py` | `read_material`、`check_rules`、`query_slots`、`save_draft` |
| `store.py` | 草稿存储。没有发布记录 |
| `report.py` | 按工具观察汇总交付结果 |
| `catalog.py` | 读取 `data/` |
| `cli.py` | 命令行入口 |

没有使用 LangChain、AutoGen 或其他 Agent 框架。循环、工具路由和轨迹都在这个包里。

`data/` 的五份文件：

| 文件 | 作用 |
| --- | --- |
| `materials.json` | M01 到 M04、M10 到 M12。M02 故意缺标题、正文和受众 |
| `rules.json` | 保证收益、零风险、立刻下单三条阻断表述 |
| `slots.json` | 各日期的占用情况。2026-11-12 的 18:00 由 SCH-1800 占用，19:00 空闲 |
| `tool_faults.json` | M04 保存失败；M11、M12 的规则超时次数不同 |
| `supplements.json` | 空对象。M02 补查后仍然缺失 |
