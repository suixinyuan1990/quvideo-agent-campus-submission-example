# AI 使用记录

本项目的需求整理、方案、代码、测试和文档，是在 Cursor 里由人指定范围、由 AI 起草并反复修改完成的。下面区分 AI 起草的内容、由人改过方向的决定，以及实际跑过的验证。没有把未发生的手工改稿写成个人修改。

## 1. AI 起草了什么

- 按短视频脚本 Agent 的题目要求，起草了用户、输入、工具、交付、动态决策和五类验收。正文现放在 [01-requirements.md](01-requirements.md)。
- 按指定目录建立了 [README.md](../README.md)、`docs/` 下其余说明、`src/`、`tests/`、`examples/` 和 `requirements.txt`。
- 比较 AdvertiseGen、AdsTrace 和 MAVE 后，导入 AdvertiseGen，并写成 [data/README.md](../data/README.md)。`prepare.py` 把属性串和广告文案拆开。
- 按题目写了 [PRD.md](../PRD.md) 的技术栈、模块边界和工具契约。
- 按 PRD 写了 `src/script_agent/`、`data/fixtures/`、`tests/` 和 `.env.example`。验收输出写到 `examples/`。
- 按审核要点写了 `tests/test_audit.py`、[TEST.md](../TEST.md) 和 `examples/audit/report.json`。
- 超时后的缩短阶梯、相同稿停止、相同改写停止，以及字幕复制旁白时只报一次数字违规。
- 本目录五份说明的终版，把调用流程、实测、AI 记录和复盘补进各自的文件。

AI 选择并实现的默认路径是：Python 3.12、自写循环、内存 JSONL、汉字二元组加 BM25 排序、剧本模型、口播 4 字/秒。这些选择写在 [02-solution.md](02-solution.md)。

## 2. 人指定的范围

这些决定改变了初稿，并留在当前仓库里：

| 决定 | 结果 |
| --- | --- |
| 先按题目写需求说明 | 形成第一版需求，随后移入 `docs/01-requirements.md`。 |
| README 只做环境、安装、运行和评审入口 | 需求正文不再放在 README。 |
| 目录按 `src/`、`tests/`、`examples/`、`data/`、`docs/`、依赖文件和 `.env.example` 安排 | 目录已落地，并在终版里按这个职责补齐正文。 |
| 先构建项目结构，不进行开发 | 目录先落地。代码在需求和 PRD 定下来之后才写。 |
| 为参考实例寻找开源数据，选最合适的一份并导入 | 使用 AdvertiseGen 的属性串作为产品事实。广告文案、38 秒和 28 秒不写进素材。 |
| 设计架构和技术栈，写入 PRD | 形成 [PRD.md](../PRD.md)。 |
| 根据相关文档进行项目开发 | 实现循环、三个工具、剧本模型和五类验收。 |
| 按素材 ID、分镜时长和检查结果逐条对照，改变时长或检索结果后核对下一步 | 审核写入 [TEST.md](../TEST.md)，得分 100/100。 |
| 列出可优化点并改掉 | 20 秒目标改到最短事实句后完成；同一数字只报一次；改写查询与上次相同时停止检索。 |
| 将对应内容补进对应文档，形成完整终版 | 五份说明、README、资料说明和 `.env.example` 按各自职责补齐。 |

人没有单独改过某一行实现。上面每一条都是对话里的范围约束，随后由 AI 改代码、测试和文档来满足。

## 3. 验证

验证都在本机用剧本模型完成，没有调用付费模型接口。

| 检查 | 命令或位置 | 结果 |
| --- | --- | --- |
| 资料拆分 | `python data/advertisegen/prepare.py` | 115669 条素材，并核对原始文件 SHA-256 |
| 依赖安装 | `python -m pip install -r requirements.txt` | 安装完成 |
| 全套测试 | `python -m pytest` | 最近一次 14 通过，0 失败，2.63 秒 |
| 五类场景 | `tests/test_agent.py`，样例在 `examples/scenarios/` | 通过 |
| 来源与修正审核 | `tests/test_audit.py`，记录在 `examples/audit/report.json` | 100/100，关键缺陷为空 |
| 参考实例命令行 | `python -m script_agent.cli --theme "详细介绍支持字幕" --duration 30 --corpus data/fixtures/materials.jsonl` | `completed`，28.0 秒，来源 P01，输出在 `examples/last-run.json` |

第一次实现后的 pytest 是 12 通过。补上审核后是 13 通过。补上「字幕与旁白相同只报一次」的测试后是 14 通过。命令行没有使用真实模型密钥。
