# 短视频脚本 Agent

帮助创作者依据产品素材和品牌规则，生成满足目标时长的可编辑脚本。本文是环境、安装、运行和评审入口。需求见 [docs/01-requirements.md](docs/01-requirements.md)。技术栈和架构见 [PRD.md](PRD.md)。

实现在 `src/script_agent/`。验收测试在 `tests/`，样例输出在 `examples/`。产品素材见 [data/README.md](data/README.md)。

## 评审入口

按这个顺序看：

1. 本文：环境、安装、运行、配置。
2. [docs/01-requirements.md](docs/01-requirements.md)：用户、目标、范围和成功标准。
3. [docs/02-solution.md](docs/02-solution.md)：调用流程、动态决策和技术取舍。
4. [docs/03-evaluation.md](docs/03-evaluation.md)：测试预期、实际结果、失败和限制。
5. `examples/`：每道验收题的输入、实际输出和 Trace。
6. [docs/04-ai-usage.md](docs/04-ai-usage.md)：AI 辅助内容、个人修改及验证。
7. [docs/05-retrospective.md](docs/05-retrospective.md)：最难问题、学习收获、下一步。

必须通过的五类场景是：正常生成、缺关键信息、无素材、工具失败、超时长后的修正或明确失败。场景定义见 [docs/01-requirements.md](docs/01-requirements.md)。

## 项目结构

```text
README.md                 # 环境、安装、运行、评审入口
PRD.md                    # 技术栈、架构和实现边界
src/                      # 项目代码与模型/工具接入
tests/                    # 可执行测试
examples/                 # 输入、实际输出、Trace
data/                     # 合成资料和规则（按题目需要）
docs/
  01-requirements.md      # 用户、目标、范围和成功标准
  02-solution.md          # 调用流程、动态决策、技术取舍
  03-evaluation.md        # 测试预期、实际结果、失败和限制
  04-ai-usage.md          # AI 辅助内容、个人修改及验证
  05-retrospective.md     # 最难问题、学习收获、下一步
requirements.txt          # Python 依赖
.env.example              # 所需变量；剧本模型无需配置
TEST.md                   # 审核叙述，实测摘要在 docs/03
```

各目录的职责：

| 路径 | 放什么 |
| --- | --- |
| `src/` | Agent 循环、模型接入、素材检索、时长估算、规则检查。 |
| `tests/` | 可重复执行的验收测试，覆盖上面五类场景。 |
| `examples/` | 与测试对应的输入、程序实际输出、工具调用 Trace。 |
| `data/` | AdvertiseGen 属性串，以及五类验收用的 P01 夹具和声明规则。 |
| `docs/` | 需求、方案、评测、AI 使用记录和复盘。不放可执行代码。 |
| `requirements.txt` | 运行期依赖。 |
| `.env.example` | 真实模型的 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME`。剧本模型无需配置。 |

## 环境

运行时是 Python 3.12。技术栈、模块边界和工具契约见 [PRD.md](PRD.md)。剧本模型验收不需要密钥。

## 安装

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

运行期依赖是 `pydantic`、`openai`、`rank-bm25` 和 `pytest`。

## 运行

默认使用剧本模型，不访问网络。下面这条会先写出 152 字、估成 38 秒，再压到 112 字、估成 28 秒，并引用 P01。结果写入 `examples/last-run.json`。

```powershell
python -m script_agent.cli --theme "详细介绍支持字幕" --duration 30 --audience "功能介绍观众" --platform "抖音" --style "口播" --corpus data/fixtures/materials.jsonl
python -m pytest
```

`介绍支持字幕` 走短稿。`介绍支持字幕的效果` 会先写出「效率提升 80%」，规则检查失败后再删掉。`运动鞋气垫` 检索为空并改写一次。这些主题是剧本模型的验收分支。`--model openai` 才调用真实模型。

每道验收题的输入、实际输出和 Trace 在 `examples/scenarios/`。最近一次命令行结果在 `examples/last-run.json`。审核记录在 `examples/audit/report.json`，叙述在 [TEST.md](TEST.md)，预期和实测在 [docs/03-evaluation.md](docs/03-evaluation.md)。最近一次 `python -m pytest` 为 14 通过、0 失败，审核 100/100。

## 配置

剧本模型不需要密钥。真实模型把 `.env.example` 复制为 `.env`，填写 `MODEL_BASE_URL`、`MODEL_API_KEY` 和 `MODEL_NAME`。`.env` 不要提交。

## 资料

产品素材使用 AdvertiseGen。可引用的只有商品属性串；数据集自带的广告文案不能当作事实。没有时长标注，38 秒和 28 秒也不会出现在素材里。

文件、示例和许可见 [data/README.md](data/README.md)。字段要求见 [docs/01-requirements.md](docs/01-requirements.md)。

## 需求

需求正文在 [docs/01-requirements.md](docs/01-requirements.md)，包括用户、目标、范围、输入、工具、动态决策、交付和必须验收。

## 本阶段不做

- 不把 AdvertiseGen 的广告文案编入检索或改写成产品事实。
- 不把 38 秒或 28 秒写进素材。这两个数只来自时长工具。
- 不生成成片，不剪辑，不配音，不上传，不排期发布。
