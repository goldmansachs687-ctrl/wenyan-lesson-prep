"""查询随技能附带的备课材料和可选的本地文言文语料库。"""

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from itertools import islice
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata


SKILL_DIR = Path(__file__).resolve().parents[1]
CORPUS_NAME = "文言文语料库"
WORDLIST = "教学参考/taotao/skills/gushiwen/references/文言词表/江西省中考文言文高频词表.md"
WORDLIST_URL = (
    "https://github.com/ichangting/taotao-skills/blob/4d6f67f4d88bcabc1f4f1fd857e0d92e7fb67575/"
    "skills/gushiwen/references/文言词表/江西省中考文言文高频词表.md"
)
WORD_HEADING = re.compile(r"###\s+([^()（）]+?)\s*(?:（([0-9]+)）|\(([0-9]+)\))\s*$")
WORD_SENSE = re.compile(r"\*\*义项\s*[0-9]*\s*[:：]\s*(.+?)\s*\*\*\s*$")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def compact(text):
    """Ignore spacing and punctuation just in the classroom-card search index."""
    return "".join(char for char in text if not char.isspace() and not unicodedata.category(char).startswith("P"))


def classroom_search(keyword, title, category, limit):
    rows = read_json(SKILL_DIR / "references" / "classroom.json")
    if not isinstance(rows, list):
        raise ValueError("classroom.json must be a list")
    needle = compact(keyword)
    topic = compact(title)
    ranked = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        work = row.get("work", "")
        if topic and topic not in compact(work):
            continue
        if category and row.get("category") != category:
            continue
        if not needle:
            rank, matched = 2, "按篇名或题型"
        elif needle == compact(row.get("term", "")):
            rank, matched = 0, "词条"
        elif any(needle in compact(row.get(key, "")) for key in ("quote", "work")):
            rank, matched = 1, "原句或篇名"
        elif needle in compact(row.get("searchQuote", "")):
            rank, matched = 1, "备查字形（引用采用 quote 原字形）"
        elif any(needle in compact(row.get(key, "")) for key in ("meaning", "pitfall", "category")):
            rank, matched = 3, "教学说明"
        else:
            continue
        ranked.append((rank, {**row, "matched_by": matched}))
    return [row for _, row in sorted(ranked, key=lambda item: item[0])[:limit]]


def find_corpus():
    configured = os.environ.get("WENYAN_CORPUS_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path.resolve() if path.is_dir() else None
    for start in (Path.cwd().resolve(), SKILL_DIR):
        for parent in (start, *start.parents):
            candidate = parent if parent.name == CORPUS_NAME else parent / CORPUS_NAME
            if candidate.is_dir():
                return candidate
    return None


def teacher_library():
    for start in (Path.cwd().resolve(), SKILL_DIR):
        for parent in (start, *start.parents):
            folder = parent / "文言文教学" / "教师备课资料"
            if (folder / "查备课笔记.py").is_file():
                return folder
    return None


def run_local_lookup(script, *params):
    if not script or not script.is_file():
        raise ValueError("这个工作区缺少该查询所需的本地资料。")
    result = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(script), *params, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=script.parent,
        timeout=20,
    )
    if result.returncode:
        raise ValueError("本地查询失败。请检查查询条件，或从资料入口查看对应索引。")
    return json.loads(result.stdout)


def manifest_metadata(directory):
    manifest = directory / "下载清单.json"
    if not manifest.is_file():
        return {}
    data = read_json(manifest)
    return {
        item["file"]: item for item in data.get("files", [])
        if isinstance(item, dict) and isinstance(item.get("file"), str)
    }


def teacher_word_search(directory, metadata, keyword, limit):
    path = directory / WORDLIST
    if not keyword or not path.is_file():
        return []
    source = metadata.get(WORDLIST, {})
    matches = []
    current = None
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            heading = WORD_HEADING.fullmatch(line)
            if heading:
                current = None
                term = heading[1].strip()
                if term == keyword:
                    current = {
                        "term": term,
                        "count": int(heading[2] or heading[3]),
                        "senses": [],
                        "source_title": "江西省中考文言文高频词表",
                        "sample_period": "2014—2025年江西省中考样本",
                        "source_url": source.get("url") or WORDLIST_URL,
                        "license_note": source.get("license_note", "仓库原创指南为 MIT，试题摘录另有出处。"),
                    }
                    matches.append(current)
            elif line.startswith("#"):
                current = None
            elif current is not None:
                sense = WORD_SENSE.fullmatch(line)
                if sense:
                    current["senses"].append(sense[1].strip())
    return matches[:limit]


def corpus_search(directory, metadata, keyword, title, limit):
    helper = directory / "查语料.py"
    spec = spec_from_file_location("wenyan_local_corpus", helper)
    module = module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    book, _, chapter = title.strip("《》").partition("·")
    rows = module.search(keyword, book.strip(), "all", metadata)
    if chapter.strip():
        chapter_key = compact(chapter)
        rows = (row for row in rows if chapter_key in compact(str(row.get("section", ""))))
    results = []
    for row in islice(rows, limit):
        match = "按原字形逐字匹配（不换字形、不补标点）" if keyword else "按篇名选取篇首片段"
        results.append({**row, "matched_by": match})
    return results


def lookup(keyword, title, category, limit):
    result = {"classroom": [], "teacher_words": [], "corpus": [], "notes": [], "corpus_available": False}
    notes = result["notes"]
    try:
        result["classroom"] = classroom_search(keyword, title, category, limit)
    except (OSError, ValueError, TypeError, AttributeError):
        notes.append("未能读取随技能附带的课堂卡片。")
    if category:
        notes.append("题型只用于筛选课堂卡片，原文和江西词表保留各自的分类口径。")
    try:
        directory = find_corpus()
    except (OSError, RuntimeError):
        directory = None
    if directory is None:
        notes.append("未找到可选的本地文言文语料库。课堂卡片仍可使用，可用 WENYAN_CORPUS_DIR 指定语料库目录。")
        return result
    try:
        metadata = manifest_metadata(directory)
    except (OSError, ValueError, TypeError, AttributeError):
        metadata = {}
        notes.append("未能读取下载清单，缺失的版本来源须另行核对。")
    try:
        result["teacher_words"] = teacher_word_search(directory, metadata, keyword, limit)
    except (OSError, UnicodeError):
        notes.append("未能读取江西词表。")
    if result["teacher_words"]:
        notes.append("江西词表频次仅代表 2014—2025 年江西省中考样本。义项标签按原表呈现，未引用原表例句。")
    if not (directory / "查语料.py").is_file():
        notes.append("本地语料目录缺少查语料.py，原文检索暂不可用。")
        return result
    if not keyword and not title:
        notes.append("仅指定题型时查课堂卡片。查本地原文需提供关键词或篇名。")
        result["corpus_available"] = True
        return result
    try:
        result["corpus"] = corpus_search(directory, metadata, keyword, title, limit)
        result["corpus_available"] = True
    except (OSError, ValueError, TypeError, AttributeError, KeyError, ImportError, SyntaxError):
        notes.append("本地原文语料暂不可读取，请检查安装文件。")
    if result["corpus_available"] and not result["corpus"]:
        notes.append("原文检索没有匹配。可尝试原字形、繁体、简体或更短的连续字词。")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyword", nargs="?", default="", help="例如：走、冀复得兔")
    parser.add_argument("--title", default="", help="篇名或书名，例如：论语")
    parser.add_argument("--category", default="", help="课堂卡片题型，例如：实词、虚词、断句")
    parser.add_argument("--limit", type=int, default=8, help="每组最多结果数，1 至 30")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--teacher", action="store_true", help="查老师笔记及原稿")
    modes.add_argument("--course", action="store_true", help="查统编课内篇目与来源")
    modes.add_argument("--dictionary", action="store_true", help="查字书与具书证的文言候选义")
    parser.add_argument("--grade", default="", help="配合 --teacher 或 --course 使用")
    parser.add_argument("--volume", default="", help="配合 --course 指定册次")
    parser.add_argument("--school-system", choices=("六三", "五四"), help="配合 --course 指定义务教育学制")
    parser.add_argument("--source", choices=("wiktionary", "kangxi", "shuowen"),
                        help="配合 --dictionary 指定查词来源")
    parser.add_argument("--text", action="store_true", help="展开原稿所在小节或课文底本")
    args = parser.parse_args()
    if args.school_system and not args.course:
        parser.error("--school-system 须配合 --course 使用。")
    if args.source and not args.dictionary:
        parser.error("--source 须配合 --dictionary 使用。")
    keyword, title, category = (value.strip() for value in (args.keyword, args.title, args.category))
    if not (compact(keyword) or compact(title) or compact(category)):
        parser.error("请提供关键词、篇名或题型。")
    if len(keyword) > 80 or len(title) > 120 or len(category) > 80 or not 1 <= args.limit <= 30:
        parser.error("关键词和题型最多 80 字，篇名最多 120 字，结果数须在 1 至 30 之间。")
    if args.teacher or args.course or args.dictionary:
        if not keyword:
            parser.error("查老师资料、课内篇目或字典时，请将关键词直接写在命令里。")
        try:
            common = [keyword, "--limit", str(args.limit)]
            if args.teacher:
                directory = teacher_library()
                params = [*common, "--grade", args.grade]
                if args.text:
                    params.append("--section")
                result = run_local_lookup(directory / "查备课笔记.py" if directory else None, *params)
            else:
                directory = find_corpus()
                if args.course:
                    params = [*common, "--grade", args.grade, "--volume", args.volume]
                    if args.school_system:
                        params.extend(("--school-system", args.school_system))
                    if args.text:
                        params.append("--text")
                    script = directory / "教学参考" / "统编课内" / "查课文.py" if directory else None
                    result = run_local_lookup(script, *params)
                else:
                    script = directory / "字书" / "扩充" / "查字典.py" if directory else None
                    if args.source:
                        common.extend(("--source", args.source))
                    result = run_local_lookup(script, *common)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            parser.exit(1, f"{error}\n")
    else:
        result = lookup(keyword, title, category, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
