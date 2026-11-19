# 离线文言字词查询

这里收录两部古字书原文，以及中文维基词典有文言书证或明确标作书面语的部分释义。用于找候选义、书证和字形关系。具体课堂释义须结合教师使用的原句、底本和采分点。

## 查询

在本目录运行。支持 Python 3.11 及更新版本，使用标准库。查询和从现有源文件重建索引均可离线运行。

```powershell
python -X utf8 查字典.py 之 --json --limit 12
python -X utf8 查字典.py 顾 --source kangxi --limit 3
python -X utf8 查字典.py 俨然 --source wiktionary --json
python -X utf8 查字典.py --stats --json
```

返回的 `headword` 保留来源字形，`locator` 给出卷、版面、记录号或维基词条书证，`source_url` 可用于回查。依次匹配原字头、来源所载异形、OpenCC 简繁候选和字书核对候选。遇一简对多繁请分别检查原字头。所截短的释文在 JSON 里带 `truncated: true`，可用 `--max-chars` 查看更长原文。

| 本地索引 | 字头或词条数 | 记录数 | 主要内容 |
| --- | ---: | ---: | --- |
| 康熙字典 | 46,890 | 47,030 | 古字书原文，另建 2,381 条来源字形关联 |
| 说文解字 | 9,815 | 9,833 | 古字书原文，另建 1,245 条来源字形关联 |
| 中文维基词典 | 5,412 | 7,608 | 4,796 条有文言引文，覆盖 3,590 个字头，3,737 条标书面语，两项重叠 925 条，另建 3,920 条来源简体关联 |

同一字头可以在同书多处出现。表中关系数按归属记录计，同一异形可关联多个义项。某些古字书用兼容字形，例如查「卿」会找到源数据字头「卿」。

## 中学备课怎样采用释义

1. 查准本句与教材版次，优先看该册课文注释、教师讲义或该卷评分参考。写给学生的释义要能放回原句，同时说明一个判断线索，例如动作对象、转折关系或指代所指。
2. 字书提供义项候选和书证。「书面语」标记与具体文言例句分别看待。同一个字换篇后重判，例如《陈太丘与友期行》的「顾」看回头这一动作，《出师表》的同字看拜访的对象。
3. 查不到一个复词时核对全句和阅读材料。兼容字形、源数据异体与简繁映射可用于找字头，课堂的通假说明由这个句子的教材或有依据的注释确定。

用江西 2014—2025 样本文言词表实际能解析出的 103 个词头检查，原索引有 102 个能找到候选字头。原查「举」「舉」漏掉《康熙字典》记录的「擧」。补查字头后，103 个都有至少一个候选来源。命中字头只衡量查得到，具体义项和词组按原句核定。资料同时保留可供人工交叉核对的现代学习型字典入口。 [高频词表](../../教学参考/taotao/skills/gushiwen/references/文言词表/江西省中考文言文高频词表.md) · [《康熙字典》手部「擧」原注](https://github.com/ksanaforge/kangxizidian/blob/d64472a760b90088a2d00fb452485340e57ca74b/xml/kx01-04-02.xml) · [人教社《文言文学习字典》](https://www.pep.com.cn/products/zhytu/gjshnj/rjjdcs/201509/t20150918_1247113.shtml) · [商务印书馆《古代汉语词典》](https://www.cp.com.cn/book/c616b263-8.html)

## 来源与加工

- **《康熙字典》**。原书为清代古籍，数字校录使用 `ksanaforge/kangxizidian` 的固定提交 `d64472a760b90088a2d00fb452485340e57ca74b`。本地原始 ZIP 含原仓库说明、GNU GPL 第 3 版许可及 60 个 XML 文件。索引保留来源正文和书证，剥去编辑标签，保留未展开的缺字实体为原标记。对 `kx01-04-02.xml` 第 5184 行编辑标签中的多余标记做一次解析修补。原始 ZIP 的 SHA-256 是 `1b5e63f9bd2bad19b6e118ac5afbecf5a1e1337c6eaef0fc7b3d0609f287db1e`。 [上游仓库固定版本](https://github.com/ksanaforge/kangxizidian/tree/d64472a760b90088a2d00fb452485340e57ca74b) · [原仓库许可](https://github.com/ksanaforge/kangxizidian/blob/d64472a760b90088a2d00fb452485340e57ca74b/LICENSE)
- **《说文解字》**。读取旁边语料库已有的 `shuowen/shuowen-data.jsonl`，取原始 `explanation`、`variants`、卷部和记录 ID。现有文件来自 Shuowen.org 数据仓库的 `6553a350763ce4feca2c5d1cc2cad7e594dc2975`，仓库以 Apache-2.0 发布。 [固定版本](https://github.com/shuowenjiezi/shuowen/tree/6553a350763ce4feca2c5d1cc2cad7e594dc2975) · [许可](https://github.com/shuowenjiezi/shuowen/blob/6553a350763ce4feca2c5d1cc2cad7e594dc2975/LICENSE)
- **中文维基词典**。署名中文维基词典贡献者，使用 Kaikki.org 的 Wiktextract 提取数据，维基词条文字按 CC BY-SA 4.0 使用。两项分类源自 2026-11-01 中文版转储，于 2026-11-02 抽取。保留同一义项下已标 `Classical-Chinese` 且有文字及出处的引文信息，亦保留原标 `literary` 的释义并显示「书面语」。简体关联取来源明示的简体形式。索引仅存中文释义、原使用标签、词性和书证出处，整理时按原字头、释义和词性去重。文言书证的断代和认可程度随原词条而异。两个原始下载的大小、记录数和 SHA-256 见 `维基词典来源.json`。 [中文维基词典](https://zh.wiktionary.org/) · [Wiktionary 版权](https://en.wiktionary.org/wiki/Wiktionary:Copyrights) · [Kaikki 文言引文分类](https://kaikki.org/zhwiktionary/%E6%BC%A2%E8%AA%9E/categories-other/hv/%E6%9C%89%E5%BC%95%E6%96%87%E7%9A%84%E6%96%87%E8%A8%80%E6%96%87%E8%A9%9E/index.html) · [Kaikki 书面语分类](https://kaikki.org/zhwiktionary/%E6%BC%A2%E8%AA%9E/tags/RY/literary/index.html) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- **简繁字形映射**。使用 Apache-2.0 版 OpenCC `STCharacters.txt`，提交 `fae2a0a911c30764e669a7d8b0591cd8e852934a`。原许可随映射保存。 [固定版本](https://github.com/BYVoid/OpenCC/blob/fae2a0a911c30764e669a7d8b0591cd8e852934a/data/dictionary/STCharacters.txt)
- **在线参考**。香港中文大学的「汉语多功能字库」可在线核对古文字形、字义和典籍用例。这里只提供网站入口。 [香港中文大学汉语多功能字库](https://humanum.arts.cuhk.edu.hk/Lexis/lexi-mf/)

## 重建与检查

```powershell
python -B -X utf8 建立索引.py
python -B -X utf8 -m unittest -v
```

需要刷新维基词义时，联网运行 `python -B -X utf8 更新维基词义.py`，再运行 `python -B -X utf8 建立索引.py --source wiktionary`。刷新会读取上游当前快照并记录来源、校验值和日期。
