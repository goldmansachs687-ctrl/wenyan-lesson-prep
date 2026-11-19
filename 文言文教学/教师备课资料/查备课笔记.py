"""只读检索教师自己的篇目笔记和已经生成的原稿索引。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
META_LINE = re.compile(r"^([^:#：\s][^:：]*?)\s*[:：]\s*(.*?)\s*$")
SEPARATORS = re.compile(r"[\s、，,；;]+")
LIST_NUMBER = re.compile(r"^[（(]?(?:\d+|[一二三四五六七八九十]+)[、.．）)]\s*")
SECTION = re.compile(r"^\s*(?:#{1,9}\s+(.+)|【((?:第\s*\d+\s*页|表格\s*\d+))】)\s*$")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\((?:<[^>]*>|[^)]*)\)")


@dataclass
class Record:
    record_type: str
    path: Path
    line_path: Path
    title: str
    metadata: dict
    headings: list[str]
    lines: list[str]
    first_line: int = 1


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in text if char.isalnum())


def inside(root: Path, path: Path) -> Path | None:
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
        return resolved
    except (ValueError, OSError, RuntimeError):
        return None


def parse_note(text: str) -> tuple[dict[str, str], list[str], int]:
    lines = text.splitlines()
    metadata = {}
    if not lines or lines[0].strip() != "---":
        return metadata, lines, 1
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return metadata, lines, 1
    for line in lines[1:end]:
        match = META_LINE.match(line)
        if match:
            key, value = match.groups()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1].strip()
            metadata[key.strip()] = value
    return metadata, lines[end + 1 :], end + 2


def read_note_records(root: Path):
    notes = root / "篇目笔记"
    if not notes.is_dir() or inside(root, notes) != notes:
        return
    for name, children, files in os.walk(notes):
        folder = Path(name)
        children[:] = sorted(
            child for child in children if inside(notes, folder / child) == folder / child
        )
        for filename in sorted(files):
            file = folder / filename
            if file.suffix.casefold() != ".md" or inside(notes, file) != file or not file.is_file():
                continue
            try:
                metadata, lines, first_line = parse_note(file.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError) as error:
                print(f"无法读取笔记 {file.relative_to(root)}：{error}", file=sys.stderr)
                continue
            metadata["核对"] = metadata.get("核对", "").strip() or "待核对"
            headings = [line.lstrip().lstrip("#").strip() for line in lines if re.match(r"^\s*#{1,6}\s", line)]
            title = metadata.get("标题") or (headings[0] if headings else file.stem)
            yield Record("教师笔记", file, file, title, metadata, headings, lines, first_line)


def read_index_records(root: Path):
    index = root / "索引" / "原稿索引.json"
    if not index.is_file() or inside(root, index) != index:
        return
    try:
        document = json.loads(index.read_text(encoding="utf-8-sig"))
        entries = document.get("records") if isinstance(document, dict) else document
        if not isinstance(entries, list):
            raise ValueError("需为记录数组或包含 records 数组的对象")
    except (OSError, UnicodeError, ValueError) as error:
        print(f"无法读取原稿索引：{error}", file=sys.stderr)
        return

    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
            continue
        source = inside(root, root / item["path"])
        if source is None or not source.is_file():
            continue
        raw_extract = item.get("extract")
        extract = inside(root, root / raw_extract) if isinstance(raw_extract, str) and raw_extract else None
        status = item.get("status", "ok")
        lines = []
        if extract is not None and extract.is_file() and extract.suffix.casefold() in {".md", ".txt"} and status in ("ok", "partial_needs_ocr"):
            try:
                lines = extract.read_text(encoding="utf-8-sig").splitlines()
            except (OSError, UnicodeError) as error:
                print(f"无法读取原稿提取文本 {extract.relative_to(root)}：{error}", file=sys.stderr)

        source_metadata = item.get("metadata", {})
        metadata = source_metadata.copy() if isinstance(source_metadata, dict) else {}
        for key in ("kind", "table_count", "page_count", "status", "年级"):
            if key in item and isinstance(item[key], (str, int)):
                metadata[key] = item[key]
        metadata["核对"] = str(metadata.get("核对") or "").strip() or "待核对"
        title = item.get("title")
        headings = item.get("headings", [])
        yield Record(
            "原稿", source, extract if lines else source,
            title if isinstance(title, str) and title else source.stem,
            metadata, [h for h in headings if isinstance(h, str)] if isinstance(headings, list) else [], lines,
        )


def grade_matches(record: Record, grade: str, root: Path) -> bool:
    if not grade:
        return True
    fields = normalize(str(record.metadata.get("年级", "")) + record.path.relative_to(root).as_posix())

    def present(label: str) -> bool:
        if label[0].isdigit():
            return re.search(rf"(?<![0-9]){re.escape(label)}", fields) is not None
        return label in fields

    if present(grade):
        return True
    groups = {
        "小学": tuple((f"{chinese}年级", f"{arabic}年级") for arabic, chinese in enumerate("一二三四五六", 1)),
        "初中": (("七年级", "初一", "7年级"), ("八年级", "初二", "8年级"), ("九年级", "初三", "9年级")),
        "高中": (("高一", "十年级", "10年级"), ("高二", "十一年级", "11年级"), ("高三", "十二年级", "12年级")),
    }
    return any(
        (grade in {school, f"{school}段"} or grade in group) and any(present(alias) for alias in group)
        for school, years in groups.items() for group in years
    )


def labels(line: str) -> set[str]:
    parts = re.split(r"[|\t]", line)
    result = set()
    for part in parts:
        part = LIST_NUMBER.sub("", part.strip().lstrip("#>*- "))
        title = re.split(r"[:：—（(=＝]", part, maxsplit=1)[0]
        result.add(normalize(title))
    return result


def best_excerpt(record: Record, terms: tuple[str, ...], expanded: bool) -> tuple:
    body_lines = [
        (i, MARKDOWN_LINK.sub("", line)) for i, line in enumerate(record.lines)
        if line.strip() and not (record.record_type == "原稿" and line.startswith(("原稿：", "状态：")))
    ]
    if not body_lines:
        return None, "\n".join(record.headings[:4]), None, 0, ""
    scores = []
    title = normalize(record.title)
    markers = []
    for index, line in body_lines:
        text = normalize(line)
        heading = SECTION.fullmatch(line)
        if heading:
            markers.append((index, heading[1] or heading[2]))
        matches = 0 if heading and text == title else sum(term in text for term in terms)
        line_labels = labels(line) if matches else set()
        exact = sum(term in line_labels for term in terms)
        short_exact = sum(len(term) == 1 and term in line_labels for term in terms)
        scores.append(((short_exact, exact, matches, int(bool(text) and not heading), -index), index))
    (_, exact, _, _, _), selected = max(scores)
    marker, locator = next(((i, name) for i, name in reversed(markers) if i <= selected), (body_lines[0][0], ""))
    boundary = next((i for i, _ in markers if i > selected), len(record.lines))
    start = max(marker, selected - (10 if expanded else 1))
    end = min(boundary, max(start + 18, selected + 8) if expanded else selected + 4)
    excerpt = []
    remaining = 2400
    for i in range(start, end):
        line = record.lines[i]
        line_limit = (1400 if i == selected else 160) if expanded else 240
        max_length = min(remaining, line_limit) - 2
        if max_length < 1:
            end = i
            break
        if len(line) > max_length:
            folded = unicodedata.normalize("NFKC", line).casefold()
            hit = next((folded.find(term) for term in terms if term in folded), 0)
            begin = max(0, hit - 55)
            line = ("…" if begin else "") + line[begin : begin + max_length] + ("…" if len(line) > begin + max_length else "")
        excerpt.append(line)
        remaining -= len(line) + 1
    return record.first_line + selected, "\n".join(excerpt).strip(), [record.first_line + start, record.first_line + end - 1], exact, locator


def rank(record: Record, phrase: str, terms: tuple[str, ...]) -> tuple[int, ...] | None:
    headings = "\n".join(record.headings)
    titles = (normalize(record.title), normalize(str(record.metadata.get("篇目", ""))), normalize(record.path.stem))
    keywords = str(record.metadata.get("关键词", ""))
    keyword_labels = {normalize(word) for word in SEPARATORS.split(keywords)}
    search_metadata = str(record.metadata.get("类型", "")) + str(record.metadata.get("位置", ""))
    searchable = set(titles) | {normalize(keywords), normalize(headings), normalize(search_metadata), normalize("\n".join(record.lines))}
    if any(not any(term in item for item in searchable) for term in terms):
        return None
    return (
        int(bool(phrase) and phrase in titles),
        sum(any(term in title for title in titles) for term in terms),
        sum(term in keyword_labels for term in terms),
        sum(term in labels(headline) for term in terms for headline in record.headings),
        sum(term in normalize(headings + "\n" + keywords) for term in terms),
    )


def search(root: Path, query: str, grade: str, limit: int, expanded: bool = False, material: str = "") -> list[dict]:
    phrase = normalize(query)
    grade = normalize(grade)
    terms = tuple(dict.fromkeys(term for part in SEPARATORS.split(query) if (term := normalize(part))))
    ranked = []
    for reader in (read_note_records, read_index_records):
        for record in reader(root):
            if (material and material != record.record_type) or not grade_matches(record, grade, root):
                continue
            score = rank(record, phrase, terms)
            if score is None:
                continue
            line, excerpt, excerpt_lines, local_exact, locator = best_excerpt(record, terms, expanded)
            score += (int(record.record_type == "教师笔记"), local_exact)
            ranked.append((score, {
                "type": record.record_type,
                "title": record.title,
                "path": record.path.relative_to(root).as_posix(),
                "line_path": record.line_path.relative_to(root).as_posix() if line is not None else None,
                "line": line,
                "locator": locator,
                "metadata": record.metadata,
                "excerpt": excerpt,
                "excerpt_lines": excerpt_lines,
            }))

    ranked.sort(key=lambda item: (tuple(-value for value in item[0]), item[1]["path"]))
    return [result for _, result in ranked[:limit]]


def print_results(results: list[dict]) -> None:
    if not results:
        print("暂无匹配的教师备课资料。")
    for result in results:
        metadata = ", ".join(f"{key}={value}" for key, value in result["metadata"].items() if value != "")
        print(f"\n## {result['title']}（{result['type']}）")
        print(f"路径：{result['path']}")
        if result["line"] is not None:
            print(f"摘录位置：{result['line_path']}:{result['line']}")
        if result["locator"]:
            print(f"小节或页码：{result['locator']}")
        print(f"信息：{metadata}")
        if result["excerpt"]:
            print(f"\n{result['excerpt']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", metavar="QUERY", nargs="?", default="", help='篇目、关键词或引文，例如 "虚词 以"')
    parser.add_argument("--grade", default="", help="按资料已注明的年级过滤，例如 七年级")
    parser.add_argument("--list", action="store_true", help="不输入关键词，列出已有资料")
    parser.add_argument("--section", action="store_true", help="展开命中小节中的上下文，最多 2400 字")
    parser.add_argument("--type", choices=("教师笔记", "原稿"), default="", help="只查一种资料")
    parser.add_argument("--limit", type=int, default=10, help="最多输出几条，默认 10")
    parser.add_argument("--json", action="store_true", help="输出 UTF-8 JSON 数组")
    args = parser.parse_args()
    if not normalize(args.query) and not args.list:
        parser.error("请输入关键词，或用 --list 列出资料。")
    if args.limit < 1:
        parser.error("--limit 必须大于 0。")

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    results = search(ROOT, args.query, args.grade, args.limit, args.section, args.type)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_results(results)


if __name__ == "__main__":
    main()
