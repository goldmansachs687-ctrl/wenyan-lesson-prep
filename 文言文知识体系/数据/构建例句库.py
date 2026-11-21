"""从统编课内正文底本中抽取 18 个常用虚词的整句例句。

只读正文底本，生成可重复构建的例句库。例句保留所在篇目、册次和出处，
供知识体系文档引用，也供 Skill 按虚词查课内例证。
"""

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "文言文语料库" / "教学参考" / "统编课内" / "正文.jsonl"
TARGET = Path(__file__).resolve().parent / "虚词例句.json"

CHARS = "而何乎乃其且若所为焉也以因于与则者之"
GRADE_ORDER = {
    "三年级": 0, "四年级": 1, "五年级": 2, "六年级": 3,
    "七年级": 4, "八年级": 5, "九年级": 6, "高中": 7,
}
OPEN_QUOTES = "“‘「『"
CLOSE_QUOTES = "”’」』"
MAX_PER_CHAR = 60
PER_GRADE = 12


def sentences(text):
    """按句末标点切句，并保证引号成对闭合。"""
    # 底本中的换行不代表句界；篇内小节号「一、」也不进入例句。
    lines = [line for line in text.split("\n") if not re.fullmatch(r"\s*[一二三四五六七八九十]\s*", line)]
    text = "".join(lines)
    pieces = [piece.strip() for piece in re.split(r"(?<=[。！？])", text) if piece.strip()]
    merged = []
    for piece in pieces:
        if merged and piece[:1] in CLOSE_QUOTES:
            merged[-1] += piece
            continue
        merged.append(piece)
    result = []
    buffer = ""
    for piece in merged:
        buffer += piece
        if sum(buffer.count(char) for char in OPEN_QUOTES) <= sum(buffer.count(char) for char in CLOSE_QUOTES):
            result.append(buffer)
            buffer = ""
    if buffer:
        result.append(buffer)
    return result


def load_rows():
    rows = []
    with SOURCE.open(encoding="utf-8-sig") as stream:
        for line in stream:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build(rows):
    index = {char: [] for char in CHARS}
    seen = {char: set() for char in CHARS}
    for row in sorted(rows, key=lambda item: (GRADE_ORDER.get(item.get("grade"), 9), item.get("title", ""))):
        text = row.get("text") or ""
        for sentence in sentences(text):
            if not 6 <= len(sentence) <= 60:
                continue
            for char in CHARS:
                if char not in sentence:
                    continue
                key = re.sub(r"\s+", "", sentence)
                if key in seen[char]:
                    continue
                seen[char].add(key)
                index[char].append({
                    "grade": row.get("grade", ""),
                    "title": row.get("title", ""),
                    "volume": row.get("volume", ""),
                    "sentence": sentence,
                    "edition": row.get("edition", ""),
                    "source_url": row.get("source_url", ""),
                })

    trimmed = {}
    for char, items in index.items():
        per_grade = {}
        kept = []
        for item in items:
            grade = item["grade"]
            count = per_grade.get(grade, 0)
            if count >= PER_GRADE:
                continue
            per_grade[grade] = count + 1
            kept.append(item)
            if len(kept) >= MAX_PER_CHAR:
                break
        trimmed[char] = kept
    return trimmed


def main():
    if not SOURCE.is_file():
        sys.exit(f"找不到正文底本：{SOURCE}")
    rows = load_rows()
    index = build(rows)
    document = {
        "built_from": SOURCE.relative_to(ROOT).as_posix(),
        "corpus_count": len(rows),
        "note": "例句按课内底本原字形抽取，仅供备课比对；课堂用字以老师所用教材为准。",
        "chars": list(CHARS),
        "index": index,
    }
    TARGET.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = sum(len(items) for items in index.values())
    print(f"已生成 {TARGET.relative_to(ROOT)}：{len(index)} 个虚词，{total} 条例句。")
    for char in CHARS:
        print(f"  {char}：{len(index[char])} 条")


if __name__ == "__main__":
    main()
