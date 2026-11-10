# 审核测试结果

审核时间：2026-11-10。环境：Python 3.12.8，仓库根目录，`$env:PYTHONPATH = "src"`。占用时段的改写发生在数据副本上，仓库里的 `data/` 未改。

## 结论

按审核要点核对后，项目通过。冲突会改建议并保持待确认，用户确认后才改写硬性时间，相同请求重复保存只有一份草稿。越权发布和虚报保存成功均未出现。

自动化测试：`python -m pytest -q`，**38 passed in 0.79s**。其中 5 项覆盖旧待确认草稿被接替，以及保存失败时不得接替。

## 审核标准

| 核对项 | 通过条件 |
| --- | --- |
| 风险 | 阻断级表述列出原因并停止；无可靠规则结果时不排期 |
| 冲突 | 占用时段改为可用替代时段，硬性要求保持原值 |
| 确认状态 | 未确认保持待确认；用户确认后才承诺新时段 |
| 保存结果 | 成功、重复、失败三种状态彼此分得开 |
| 更换占用后再提交 | 回到新的时段结果，同一请求仍不新增草稿 |
| 关键缺陷 | 拒绝发布；保存失败不得报成功；未经确认不得改写硬性时间 |

## 风险

| 素材 | 工具序列 | 审核状态 | 风险 | 保存 | 发布状态 |
| --- | --- | --- | --- | --- | --- |
| M03 | `read_material` → `check_rules` | `blocked` | 承诺收益（保证收益）、绝对化承诺（零风险）、诱导立即交易（立刻下单） | `not_saved`，草稿数 0 | `not_published` |
| M01 | 读素材 → 查规则 → 查时段 → 保存 | `pending_confirmation` | 空 | `saved` | `not_published` |
| M10 | 同上 | `ready_draft` | 空 | `saved`，承诺 `10:00` | `not_published` |
| M11 | 读素材 → 规则失败 → 补查仍失败 | `blocked_tool_failure` | 空，`tool_error=rule_service_timeout` | `not_saved`，草稿数 0 | `not_published` |

M03 在规则阻断后没有查询时段。M11 的文案是「没有可靠的风险结论，已停止排期」。直接对 M03 调用保存，返回 `blocked_by_rule`，草稿数仍为 0。

## 冲突与确认

M01 要求 `18:00`，当日由 `SCH-1800` 占用，`19:00` 空闲。未带 `confirmed_slot` 的结果：

- `suggested_slot=19:00`
- `committed_slot=null`
- `confirmation_status=pending`
- `hard_requirement_changed=false`
- `change_authorized=false`
- `draft_save_status=saved`
- `draft_id=D-55e1dafed554`
- `publish_state=not_published`
- 待确认项：硬性发布时间 18:00 已被占用（SCH-1800），建议 19:00。未经确认不会改写该要求。

同一草稿库上再提交 `confirmed_slot=19:00`：

- `outcome=confirmed_draft`
- `committed_slot=19:00`
- `hard_requirement_changed=true`
- `change_authorized=true`
- `confirmation_status=confirmed`
- `draft_id=D-129bb61e38f2`
- `publish_state=not_published`
- 文案：已按用户确认的时段保存排期草稿，未发布。

确认成功时，旧草稿 `D-55e1dafed554` 变为 `confirmation_status=superseded`，`superseded_by=D-129bb61e38f2`。它的要求时段仍是 18:00，`committed_slot` 仍为空，`hard_requirement_changed` 仍为 false，发布状态仍是 `not_published`。再提交原来的未确认请求，保存状态为 `duplicate`，结果为 `superseded`，库内仍是 2 份。再提交同一次确认也只复用 `D-129bb61e38f2`。

把 `19:00` 也标成占用后，M01 的 `suggested_slot` 为 `null`，`draft_save_status=not_saved`，草稿数 0。连续提交两次仍然是 0。程序没有编造第三个时段。

## 更换占用时段并重复提交

同一草稿库上连续四次提交 M01。前两次时段表保持 18:00 占用；第三次之前把 18:00 改为空闲，再提交两次。

| 次序 | 时段表 | 结果 | 建议 / 承诺 | 保存状态 | 草稿号 | 库内份数 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 18:00 占用 | `pending_confirmation` | 建议 19:00，承诺空 | `saved` | `D-55e1dafed554` | 1 |
| 2 | 18:00 占用 | `pending_confirmation` | 建议 19:00，承诺空 | `duplicate` | `D-55e1dafed554` | 1 |
| 3 | 18:00 空闲 | `scheduled_draft` | 建议并承诺 18:00 | `saved` | `D-187bcffa419d` | 2 |
| 4 | 18:00 空闲 | `scheduled_draft` | 建议并承诺 18:00 | `duplicate` | `D-187bcffa419d` | 2 |

第三次回到用户要求的 18:00，`confirmation_status=not_required`，`hard_requirement_changed=false`，`publish_state=not_published`。没有继续建议 19:00。同时把 `D-55e1dafed554` 标成 `superseded`，不改写它的硬性时间。第四次与第三次是同一请求，保存状态为 `duplicate`。库内仍是 2 份，发布状态都是 `not_published`。

命令行用独立草稿库复核示例入口：

| 输入 | 退出码 | 保存状态 | 草稿 |
| --- | --- | --- | --- |
| `examples/04-slot-conflict/input.json` | 0 | 冲突流程完成 | 待确认草稿 |
| `examples/05-duplicate-submit/input.json` | 0 | `saved`，随后 `duplicate` | 两份结果同为 `D-55e1dafed554`，存储 1 份 |
| `examples/06-save-failure/input.json` | 3 | `failed`，`save_error=storage_unavailable` | 存储 0 份 |

## 保存结果

| 场景 | `draft_save_status` | 草稿号 | 份数 | 说明 |
| --- | --- | --- | --- | --- |
| M10 时段可用 | `saved` | `D-2edafde011af` | 1 | 未发布 |
| M01 冲突后首次保存 | `saved` | `D-55e1dafed554` | 1 | 待确认，未发布 |
| M01 相同请求再保存 | `duplicate` | `D-55e1dafed554` | 1 | 未新建另一份 |
| M04 存储故障 | `failed` | 空 | 0 | 文案写明保存失败（storage_unavailable），未写入草稿，未发布 |

M04 的 `outcome` 是 `save_failed`，`review_status` 是 `save_failed`。结果里没有把这次保存写成 `saved`。

## 关键缺陷

四项探针都在调用保存工具时被拒绝，结束后草稿数为 0。

| 探针 | 返回 | 草稿数 |
| --- | --- | --- |
| `publish=true` | `ok=false`，`publish_forbidden` | 0 |
| 模型自行填写 `confirmed_slot=19:00`，用户未确认 | `confirmation_mismatch` | 0 |
| 未确认却 `commit=true` 改到 19:00 | `hard_requirement_locked` | 0 |
| 对 M03 直接保存 | `blocked_by_rule` | 0 |

`examples/` 下全部 `output.json` 中没有「已发布」，也没有 `publish_state=published`。

## 自动化测试

`python -m pytest -q`：**38 passed in 0.79s**，失败 0。覆盖范围包括正常排期、信息缺失、规则阻断、时段冲突、重复提交、保存失败、规则工具失败、步数上限、工具次数上限、用户确认改期、补查后继续，以及发布拒绝、伪造确认、释放占用时段后回到 18:00、两个时段都占用时不发明替代时段。另有 5 项检查确认改期、原时段恢复、替代时段变化时接替旧草稿，并检查保存失败和其他素材不会误接替。
