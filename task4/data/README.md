# 资料

当前产品素材是 [AdvertiseGen](https://huggingface.co/datasets/shibing624/AdvertiseGen)。它用来约束「脚本里的产品事实必须来自给定素材；素材没写的功效和数字不能补上」。

这份数据里没有目标时长、分镜或估算秒数。验收用的小夹具在 `data/fixtures/`：`materials.jsonl` 只有 P01「支持字幕」，`rules-disclaimer.jsonl` 是一条必须原文出现的声明。AdvertiseGen 的广告文案仍然不能进入检索。

## 为什么选它

题目里的参考实例是：素材 P01 只写了「支持字幕」；用户要 30 秒脚本；首稿估成 38 秒后应压缩并重新估算，修正结果若为 28 秒，输出要有分镜、P01 引用和总时长；没有效果数据时，不能写「效率提升 80%」。项目以后要交实际生成和检查结果，所以语料要是可核验的公开材料，而不是临时编的一句产品事实。

比较过三份公开数据：

| 数据集 | 和本题的关系 | 未采用的原因 |
| --- | --- | --- |
| AdvertiseGen | 中文商品属性是输入，广告文案是输出。发布说明写明：根据属性生成文案时，事实一致性是重点。 | 采用。 |
| [AdsTrace](https://huggingface.co/datasets/Xiuze/AdsTrace) | 2833 条电商短视频，时长约 6 到 46 秒，带转写和投放指标。 | 商品侧主要是名称，不是可引用的属性事实。转写是广告口播，投放 ROI 也不是产品功效。许可证为 CC BY-NC 4.0，并含帧和音频。 |
| [MAVE](https://github.com/google-research-datasets/MAVE) | 英文商品属性带原文位置，适合核对属性是否真的出现过。 | 正文要另行申请 Amazon Review Data (2018)。语言不是中文，许可证为 CC BY-NC 4.0。 |

时长从 38 秒改到 28 秒是估算工具的结果，不是语料字段。没有任何开源集同时给出「只含一条产品事实、30 秒目标、两次估算秒数、品牌规则」。属性事实和「不能补数字」这一条，AdvertiseGen 对得上；秒数仍要由时长工具产生。

## 和参考实例的对应关系

可引用的产品事实只有 `documents.jsonl` 的 `body`。`reference_summaries.jsonl` 是数据集自带的广告文案，每条 `citable` 都是 false，不能当作素材，也不能写进旁白。

用 `AG-dev-000533` 代替「P01 只有支持字幕，却写出效率提升 80%」：

| 字段 | 内容 |
| --- | --- |
| 来源 ID | `AG-dev-000533` |
| `body` | `类型#上衣*材质#棉*风格#简约*衣样式#衬衫*衣领型#翻领*衣款式#拼接` |
| 属性里有的材质 | 棉 |
| 文案里多出来的说法 | 「100%高支棉」「最抗皱不透」「袖口开叉」「全包边」 |

`body` 没有百分数。文案中的「100%」不能写进脚本，和「效率提升 80%」是同一类错误。全库 521 条文案含有百分数或「倍」，且该片段不在对应 `body` 中。另有 36342 条文案含 `<UNK>`，是公开发布文本里的占位，同样不能引用。

185 条素材只有一个属性。属性越少，文案越容易写出素材里没有的东西。生成时仍只引用 `body`。

30 秒、38 秒、28 秒不在这 115669 条里。用户给出目标时长后，由时长估算工具返回秒数；压到不超过目标时长之后，交付才写分镜、来源 ID 和总时长。生成结果在 `examples/`，对照结论在 [docs/03-evaluation.md](../docs/03-evaluation.md)。

## 文件

```text
data/advertisegen/
  train.json                 # 原始训练集，114599 行
  dev.json                   # 原始验证集，1070 行
  prepare.py                 # 拆成素材和不可引用文案
  documents.jsonl            # 115669 条可引用素材
  reference_summaries.jsonl  # 同 ID 的广告文案，citable 为 false
  manifest.json              # 行数与原始文件校验值
```

镜像只发布了 `train.json` 和 `dev.json`。数据集卡片写的测试集约 3k 条，不在这两个文件里。

原始文件 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `train.json` | `29f242f077fe14ba03fcb7c46f942d53fbc1a30fea89bf9c5bfc41e39f073877` |
| `dev.json` | `96b63cfd9fd0faca122a5747597f46ff835f19d9b1d3634f4b71f8a5f9487cc1` |

重新生成拆分结果：

```text
python data/advertisegen/prepare.py
```

这只改写 `documents.jsonl`、`reference_summaries.jsonl` 和 `manifest.json`，不下载数据，也不生成脚本。

## 字段

每条素材包含：

| 字段 | 含义 |
| --- | --- |
| `source_id` | `AG-train-000001` 这种按文件顺序编号的 ID。 |
| `split` / `row_index` | 来自 `train` 或 `dev` 的第几行，从 1 计。 |
| `body` | 原始属性串，引用必须能在这里逐字找到。 |
| `attributes` | 按 `*` 分段、再按第一个 `#` 拆开的键值。顺序保留，重复键也保留。 |
| `dataset` | `shibing624/AdvertiseGen`。 |

属性串形如 `类型#上衣*材质#棉`。键和值都非空；导入时 115669 行全部按这个格式拆开。

## 使用时的限制

- 来源是清华大学 CoAI 小组的电商广告数据，经千言发布，Hugging Face 镜像为 [shibing624/AdvertiseGen](https://huggingface.co/datasets/shibing624/AdvertiseGen)。商品是服饰属性，不是短视频功能说明，也没有「支持字幕」这一条。
- 卡片写训练集约 114k、验证集约 1k、测试集约 3k。导入文件的实际行数是训练集 114599、验证集 1070，没有测试集。
- 镜像卡片标注 CC BY 4.0。千言页面写明仅供研究、学习，禁止商用，使用时注明作者，所有权归原作者。本仓库按更严的千言说明使用，不把正文再许可成项目自己的许可证。
- 论文：Zhihong Shao 等，Long and Diverse Text Generation with Planning-based Hierarchical Variational Model，EMNLP-IJCNLP 2019。
- 正式介绍页：[千言 AdvertiseGen](https://www.luge.ai/#/luge/dataDetail?id=9)。
