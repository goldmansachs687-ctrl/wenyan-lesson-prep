"""打包公开参考语料和备课 Skill，供另一台电脑解压调用。"""

import hashlib
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile


CORPUS = Path(__file__).resolve().parent
PROJECT = CORPUS.parent
SKILL = ".agents/skills/wenyan-lesson-prep"
COURSE = "教学参考/统编课内"
DICTIONARY = "字书/扩充"
TEACHER_TOOLS = "文言文教学/教师备课资料"
WORDS = "教学参考/taotao/skills/gushiwen/references/文言词表/江西省中考文言文高频词表.md"
WORD_LINE = re.compile(r"^###\s+.+?[（(][0-9]+[）)]\s*$|^\*\*义项\s*[0-9]*\s*[:：].+\*\*\s*$")

PORTABLE_FILES = (
    "查语料.py",
    *(f"{COURSE}/{name}" for name in ("义务教育.json", "高中.json", "正文.jsonl", "查课文.py", "课内目录.md")),
    *(f"{DICTIONARY}/{name}" for name in (
        "查字典.py", "康熙字典.sqlite3", "说文解字.sqlite3", "维基文言词义.sqlite3",
        "康熙源文件.zip", "OpenCC-STCharacters.txt", "OpenCC-LICENSE.txt", "SOURCES.md",
        "维基词典来源.json",
    )),
    "字书/shuowen/LICENSE",
    "字书/shuowen/README.md",
    "语料收录说明.md",
    "语料库目录.md",
    "fetch_corpora.py",
    # 复习与五四学制内容已并入发布版，离线包不再分 Codex 版 / 复习版。
    "教学参考/复习/中考高考文言文复习.md",
    "教学参考/统编课内/五四学制.json",
    "教学参考/统编课内/五四学制课内目录.md",
    "教学参考/统编课内/正文-五四.jsonl",
)

GUIDE = """# 文言文备课 Skill · 包内使用说明

第一次拿这个包、不知道该打开什么、输哪条命令：先看同目录的 [README.md](README.md)。只想翻资料、打印题，**完全不用装 AI** —— 直接打开 [知识体系入口](文言文知识体系/从这里开始.md)，诊断卷、L0—L5 题库学生版、讲解范例都是 Markdown，可直接打印。

## 用 AI 备课

完整解压后，用 Codex 打开同一目录，在新对话输入 `$wenyan-lesson-prep`，接着说课文、年级和要求。

> $wenyan-lesson-prep 核对七年级《论语》十二章的选段，设计一段比较两处「而」的课堂活动，附单独的教师答案。

在 DeepSeek Harness 打开同一解压目录后，可尝试 `/wenyan-lesson-prep`；未识别时，请它先读取 `.agents/skills/wenyan-lesson-prep/SKILL.md`。

## 先跑一次自检

在项目根目录执行（只读，不需要写权限）：

    python -B -X utf8 验收备课.py --read-only

显示「共通过 8/8 项，跳过 1 项」即课文、字典、题库、知识体系均可读。可写环境下去掉 `--read-only` 可跑 9/9 全量。

## 包里有什么

- [统编课内目录](文言文语料库/教学参考/统编课内/课内目录.md) 是篇目和正文入口；换版过渡册与古籍底本会注明来源。
- [离线字典](文言文语料库/字书/扩充/SOURCES.md) 提供《康熙字典》《说文解字》和中文维基词典的语境候选义。
- [试讲样例](文言文备课样例/论语的两处而/教案.md) 可查看课堂步骤及配套练习。
- [文言文知识体系](文言文知识体系/从这里开始.md) 按六级能力（L0 认读 → L5 应试稳定）给出学习路径、分级题库、诊断定级和讲解范例。
- [语料收录说明](文言文语料库/语料收录说明.md) 说明本包收录了哪些语料、完整语料如何自行补全，以及各来源的许可。
- [语料库目录](文言文语料库/语料库目录.md) 是 24 个数据源的调研与许可清单。

教师档案随各自项目管理。要建立自己的档案，可以对 Codex 说「把这些讲义归档到教师原始资料，为我重建索引」，并提供自己的文件。**本包不含任何老师原稿、备课产物、篇目笔记或索引摘录。**

Word 文字检索使用 Python 标准库；新 PDF 文本提取可用带 pypdf 的 Python。
"""


def add_project_path(archive, relative):
    path = PROJECT / relative
    if not path.is_file():
        raise FileNotFoundError(relative)
    archive.write(path, relative)


def archive_wordlist(archive, source):
    original = (CORPUS / WORDS).read_text(encoding="utf-8-sig")
    lines = [line for line in original.splitlines() if WORD_LINE.fullmatch(line)]
    headwords = sum(line.startswith("###") for line in lines)
    if not headwords:
        raise ValueError("没有可打包的中考词表条目")
    data = ("\n".join([
        "# 江西省中考文言文高频词表词头索引", "",
        "选录词头、次数和候选义项标签。例句可从原项目查询。", source["url"], "",
        *lines, "",
    ])).encode("utf-8")
    archive.writestr("文言文语料库/" + WORDS, data)
    return {
        **source,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "count": headwords,
        "unit": "词头",
        "adaptation": "选录词头、次数和候选义项标签。",
    }


def build(output):
    manifest = json.loads((CORPUS / "下载清单.json").read_text(encoding="utf-8-sig"))
    records = []
    temporary = output.with_name(output.name + ".part")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            for relative in (
                f"{SKILL}/SKILL.md", f"{SKILL}/scripts/lookup.py", f"{SKILL}/agents/openai.yaml",
                f"{SKILL}/references/classroom.json", f"{SKILL}/references/lesson-design.md",
                *(f"{TEACHER_TOOLS}/{file}" for file in (
                    "资料归档.py", "生成原稿索引.py", "查备课笔记.py", "生成篇目导航.py", "篇目笔记模板.md",
                )),
                *(f"文言文备课样例/论语的两处而/{file}" for file in ("教案.md", "学生练习.md", "教师答案.md")),
                "README.md", "验收备课.py",
                *("文言文语料库/" + name for name in PORTABLE_FILES),
            ):
                add_project_path(archive, relative)
            for source in manifest["files"]:
                filename = source["file"]
                if filename == WORDS:
                    records.append(archive_wordlist(archive, source))
                elif (
                    filename.startswith("原文/ect-krp/")
                    or filename in {
                        "原文/chinese-poetry/LICENSE", "原文/chinese-poetry/论语/README.md",
                        "原文/chinese-poetry/论语/lunyu.json", "教学参考/taotao/LICENSE",
                        "教学参考/reciting-us/LICENSE", "教学参考/reciting-us/PROVENANCE.md",
                        "教学参考/初中古诗文旧版/LICENSE",
                    }
                ):
                    add_project_path(archive, "文言文语料库/" + filename)
                    records.append(source)
            archive.writestr("开始使用.md", GUIDE)
            for path in sorted((PROJECT / "文言文知识体系").rglob("*")):
                if path.is_file() and path.suffix in {".md", ".py", ".json"}:
                    archive.write(path, path.relative_to(PROJECT).as_posix())
            archive.mkdir(f"{TEACHER_TOOLS}/原始资料/")
            archive.mkdir(f"{TEACHER_TOOLS}/篇目笔记/")
            archive.writestr("文言文语料库/下载清单.json", json.dumps(
                {"files": records, "failures": []}, ensure_ascii=False, indent=2
            ) + "\n")
            # 另存完整来源清单，供需要补齐全部语料的人使用（不参与验收）。
            archive.writestr("文言文语料库/下载清单-完整.json", json.dumps(
                manifest, ensure_ascii=False, indent=2
            ) + "\n")
        with ZipFile(temporary) as archive:
            if archive.testzip() is not None or len(set(archive.namelist())) != len(archive.namelist()):
                raise ValueError("便携包校验失败")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else PROJECT / "文言文备课-Codex.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    build(target)
    print(f"{target} · {target.stat().st_size:,} 字节")
