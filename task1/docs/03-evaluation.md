# 评估

## 如何复核

在仓库根目录执行：

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
```

本次在 Python 3.12.8、pytest 9.2.0 上的结果是 `38 passed in 0.76s`。示例文件由 `python -m scheduling_agent.build_examples` 生成，`tests/test_examples_match.py` 会再跑一遍并与已提交文件比较。

下面的“实际结果”来自这些已提交输出，不是手写预期。

## 验收结果

| 场景 | 文件 | 预期 | 实际 |
| --- | --- | --- | --- |
| 正常排期 | `examples/01-normal/` | 无风险，按 10:00 保存草稿，未发布 | `outcome=scheduled_draft`，`draft_save_status=saved`，`committed_slot=10:00`，`publish_state=not_published`，草稿 `D-2edafde011af` |
| 信息不足 | `examples/02-missing-info/` | 补查后仍缺字段，不保存 | 两次 `read_material`，第二次依据含“补查”。`outcome=insufficient_information`，待确认项列出标题、正文、受众，`store_draft_count=0` |
| 规则风险 | `examples/03-rule-risk/` | 列出风险并阻断 | 风险为承诺收益（保证收益）、绝对化承诺（零风险）、诱导立即交易（立刻下单）。没有时段查询，没有草稿 |
| 时段冲突 | `examples/04-slot-conflict/` | 建议 19:00，待确认，不改硬性要求，不称已发布 | 查询返回“18:00 已被占用（SCH-1800），可用替代时段 19:00”。随后 `commit=false`。`suggested_slot=19:00`，`committed_slot=null`，`hard_requirement_changed=false` |
| 重复提交 | `examples/05-duplicate-submit/` | 同一请求只有一份草稿 | 两次结果的草稿都是 `D-55e1dafed554`。保存状态依次为 `saved`、`duplicate`。`store_draft_count=1` |
| 保存失败 | `examples/06-save-failure/` | 明确失败，不能报成功 | `outcome=save_failed`，`save_error=storage_unavailable`，`draft_id=null`，`store_draft_count=0`。消息为“草稿保存失败（storage_unavailable），未写入草稿，未发布。” |
| 工具失败 | `examples/07-tool-failure/` | 没有可靠规则结果时不排期 | 两次规则调用都失败。第二次依据为补查。`tool_error=rule_service_timeout`，`risk_reasons=[]`，没有草稿 |
| 步数上限 | `examples/08-step-limit/` | 未完成 | `run_status=incomplete`，原因“已达到执行步数上限（2），任务未完成” |
| 工具次数上限 | `examples/09-tool-call-limit/` | 未完成，并留下被拦住的动作 | 已执行读取和规则检查。模型接下来要 `query_slots`，`stopped.executed=false`。原因“已达到工具调用次数上限（2），任务未完成” |
| 用户确认 | `examples/10-confirmed-alternative/` | 同意后才改写硬性时间，仍未发布 | `committed_slot=19:00`，`hard_requirement_changed=true`，`change_authorized=true`，`publish_state=not_published` |
| 补查后继续 | `examples/11-transient-then-schedule/` | 一次可重试失败后继续，而不是一律阻断 | 第一次规则调用失败，第二次通过，然后保存 13:00 草稿 |

测试还覆盖了共享数据之外的行为：把 M01 的 18:00 改成空闲后按原时间排期；19:00 也占用时不发明替代时段；补查资料补齐 M02 后继续排期；模型永不结束时工具调用仍停在上限；直接调用保存工具时，发布标记、伪造确认和规则风险都不能写入草稿。

同一草稿库上的确认边界由 `tests/test_decisions.py` 实测，不写入 `examples/`，因为示例 10 每次都使用空草稿库：

| 场景 | 预期 | 实际 |
| --- | --- | --- |
| 先保存 M01 待确认，再在同一库确认 19:00 | 新草稿已确认且未发布；旧草稿被接替，硬性时间不改 | 新草稿 `D-129bb61e38f2`，`publish_state=not_published`。旧草稿 `D-55e1dafed554` 为 `superseded`，`committed_slot=null`，`hard_requirement_changed=false` |
| 再提交原来的未确认请求 | 不新增草稿 | `draft_save_status=duplicate`，`outcome=superseded`，库内仍是 2 份 |
| 待确认之后把 18:00 改为空闲再提交 | 回到 18:00，并接替旧建议 | `outcome=scheduled_draft`，`committed_slot=18:00`，旧草稿 `superseded` |
| 已有待确认草稿时，M01 的保存工具失败 | 明确失败，旧草稿仍待确认 | `draft_save_status=failed`，`save_error=storage_unavailable`，`store_draft_count=1` |
| 同库再保存 M10 | 不接替 M01 | M01 仍是 `pending`，结果里没有 `superseded_draft_ids` |

## 轨迹里怎么核对决策

每条工具步骤包含：

- `step`：第几次实际执行的工具
- `tool` 和 `arguments`：动作与参数
- `decision_basis`：为什么选择这一步
- `result_summary`：返回摘要
- `next_action`、`next_arguments`、`next_decision_basis`：看到结果后的下一步和依据

M01 冲突轨迹的关键后续动作是：时段查询返回占用后，下一步参数为 `suggested_slot=19:00`、`commit=false`。M10 在同时段查询返回可用后，下一步参数为 `suggested_slot=10:00`、`commit=true`。

## 失败

最终测试没有失败项。开发过程中有一条安全测试曾期望“伪造确认”直接返回 `hard_requirement_locked`。实际工具先返回 `confirmation_mismatch`，因为模型声明的确认时段和用户请求不一致；用户确实没有确认、模型又要求承诺新时间时，才返回 `hard_requirement_locked`。测试已改成同时断言这两种拒绝。这不是验收场景的产品失败。

远程模型没有在本次评估中对真实接口跑通。解析测试只覆盖了本地样例字符串。因此不能把示例轨迹说成某个线上模型的输出。

## 限制

- 默认决策可以被逐行读到。它能随观察改变动作，但不是本次提交里在线生成的大模型输出。
- 一次请求处理一条素材。`repeat` 只是入口层把同一请求跑多次，用来证明草稿库去重。
- 用户确认替代时段，或原时段恢复可用后按原时间保存，都会新增一份草稿，并把同一版本上的旧待确认草稿标成 `superseded`。重复旧请求返回 `duplicate`，结果是 `superseded`，不会再增殖，也不会把硬性时间改掉。
- 替代时段只选同一日期中更晚的第一个空闲时刻，没有业务日历。
- 草稿身份包含标题、正文、渠道、受众和内容版本。只改其中一个就会被视为新请求。
- 保存失败示例依赖 `data/tool_faults.json`。去掉这段故障后，M04 会变成正常草稿。
- 步数上限在下一次决策开始前生效，所以轨迹里不一定有“想做但没做”的动作。工具次数上限会记下这个动作，示例 09 就是这种记录。
