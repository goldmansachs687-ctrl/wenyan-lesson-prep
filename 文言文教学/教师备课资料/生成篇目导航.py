"""对照课内目录和教师资料中的篇目标题，生成按学段浏览的导航。"""

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent.parent
COURSES = PROJECT / "文言文语料库" / "教学参考" / "统编课内"
INDEX = ROOT / "索引"
SECTION_NUMBER = re.compile(r"^(?:第[一二三四五六七八九十0-9]+(?:则|篇|课)|[一二三四五六七八九十0-9]+[、.．])")
PART_ENDING = re.compile(r"(?:[（(](?:原文|译文|全文|教案|节选|原文与译文)[）)]|原文|译文|教案)$")
HEADING = re.compile(r"^\s*#{1,9}\s+(.+)$")


def key(text):
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold() if char.isalnum())


def title_key(text):
    text = text.strip().lstrip("《〈").rstrip("》〉")
    text = SECTION_NUMBER.sub("", text).strip()
    text = PART_ENDING.sub("", text).strip()
    return key(text)


def markdown_label(value):
    return value.replace("[", r"\[").replace("]", r"\]")


def link(value, path):
    return f"[{markdown_label(value)}]({quote(path, safe='/')})"


def indexed_titles(course_titles):
    matches = defaultdict(list)
    data = json.loads((INDEX / "原稿索引.json").read_text(encoding="utf-8"))["records"]
    for record in data:
        path = ROOT / record["path"]
        extract = ROOT / record["extract"] if record.get("extract") else None
        if not path.is_file():
            continue
        found = set()

        def add(title, label, line):
            normalized = title_key(title)
            if len(normalized) < 1 or (normalized, label) in found:
                return
            found.add((normalized, label))
            matches[normalized].append((path, label, extract, line))

        for title in {path.stem, record["title"]}:
            add(title, "题名", None)
        if record["status"] not in {"ok", "partial_needs_ocr"} or extract is None or not extract.is_file():
            continue
        previous = ""
        for number, text in enumerate(extract.read_text(encoding="utf-8").splitlines(), 1):
            if match := HEADING.match(text):
                name = match[1].strip()
                add(name, name, number)
                previous = name
            elif re.fullmatch(r"\s*(?:[一二三四五六七八九十0-9]+[、.]\s*)?[《〈][^》〉\n]{1,22}[》〉](?:译文|原文)?\s*", text):
                name = text.strip()
                if title_key(previous) != title_key(name):
                    add(name, name, number)
                    previous = name
            elif len(text) <= 35 and title_key(text) in course_titles:
                name = text.strip()
                if title_key(previous) != title_key(name):
                    add(name, name, number)
                    previous = name
    return matches


def course_rows():
    for filename in ("义务教育.json", "高中.json"):
        with (COURSES / filename).open(encoding="utf-8-sig") as stream:
            yield from json.load(stream)["entries"]


def generate():
    entries = list(course_rows())
    course_titles = {title_key(name) for row in entries for name in (row["title"], *row.get("aliases", []))}
    materials = indexed_titles(course_titles)
    notes = {title_key(path.stem): path for path in (ROOT / "篇目笔记").glob("*.md")}
    groups = defaultdict(list)
    searched = []
    for row in entries:
        title = row["title"]
        variants = {title_key(name) for name in (title, *row.get("aliases", []))}
        candidates = {}
        for variant in sorted(variants):
            for source, label, read, line in materials.get(variant, []):
                candidates.setdefault(source, {}).setdefault(label, (read, line))
        note = notes.get(title_key(title))
        if not candidates and not note:
            continue
        searched.append((row["grade"], row["volume"], title))
        chunks = [f"### {title}"]
        if note:
            chunks.extend(["", link("篇目笔记", "../" + note.relative_to(ROOT).as_posix())])
        if candidates:
            chunks.append("")
            for path, spots in sorted(candidates.items()):
                original = link(path.name, "../" + path.relative_to(ROOT).as_posix())
                positions = []
                for label, (read, line) in spots.items():
                    if line:
                        hint = f"{label}，摘录第 {line} 行"
                        positions.append(link(hint, read.relative_to(INDEX).as_posix()))
                chunks.append("- " + original + (" · " + " · ".join(positions) if positions else ""))
        groups[(row["grade"], row["volume"])].append(chunks)
    output = [
        "# 按课内篇目翻老师资料", "",
        f"统编目录中有 {len(searched)} 条册次记录能从现有教师资料的题名、栏目或单篇笔记对上。",
        "原稿里可同时收课内选段和拓展阅读。条目仅表示标题关联，备课时仍可到教材目录核对册次。",
        "", "[全部教师原稿](原稿目录.md) · " + link("统编教材目录", "../../../文言文语料库/教学参考/统编课内/课内目录.md"),
    ]
    for group, entries_by_volume in groups.items():
        output.extend(["", f"## {group[0]} {group[1]}"])
        for entry in entries_by_volume:
            output.extend(["", *entry])
    target = INDEX / "按篇目找老师资料.md"
    staged = target.with_suffix(".tmp")
    staged.write_text("\n".join(output) + "\n", encoding="utf-8")
    staged.replace(target)
    print(f"按 {len(searched)} 条册次记录生成教师资料导航。")


if __name__ == "__main__":
    generate()
