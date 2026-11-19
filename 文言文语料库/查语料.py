"""在已下载的文言文原文和字书里查找字词，保留来源与版本。"""

import argparse
from itertools import islice
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
EARLY_NAMES = {
    "KR1h0004": "论语", "KR1h0001": "孟子", "KR3c0005": "韩非子", "KR3a0002": "荀子",
    "KR5c0126": "庄子", "KR2e0003": "战国策", "KR3j0002": "墨子", "KR3j0009": "吕氏春秋",
    "KR5c0124": "列子", "KR1j0002": "尔雅",
}


def records(path):
    if path.is_file():
        with path.open(encoding="utf-8-sig") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def json_file(path, default):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def sources(selected):
    # Short classroom material first; each record retains its own dataset identity.
    if selected in {"all", "school"}:
        path = Path("教学参考/reciting-us/RecitingUsApp/web/config/articles.json")
        for row in json_file(ROOT / path, {}).get("articles", []):
            yield path, row.get("title", ""), row.get("id", ""), row["text"], "背书哇课文原文"
    if selected in {"all", "lunyu"}:
        path = Path("原文/chinese-poetry/论语/lunyu.json")
        for row in json_file(ROOT / path, []):
            yield path, "论语", row["chapter"], "\n".join(row["paragraphs"]), "chinese-poetry 版"
    if selected in {"all", "gujilab"}:
        path = Path("原文/gujilab/corpus.jsonl")
        for row in records(ROOT / path):
            yield path, row["source"], row.get("chapter") or row["id"], row["content"], row.get("_source", "gujilab 版")
    if selected in {"all", "ect"}:
        for key, title in EARLY_NAMES.items():
            path = Path(f"原文/ect-krp/jsonl/{key}.jsonl")
            for row in records(ROOT / path):
                yield path, title, row["id"], row["text"], "Kanseki Repository · 无标点整理版"
    if selected == "shuowen":
        path = Path("字书/shuowen/shuowen-data.jsonl")
        for row in records(ROOT / path):
            word, explanation = row.get("wordhead", ""), row.get("explanation", "")
            if word and isinstance(explanation, str):
                yield path, "说文解字", f"{word} · 字条 {row.get('id', '')}", f"{word}：{explanation}", "shuowen.org 版"


def search(keyword, title_filter, source, metadata):
    for path, title, section, body, edition in sources(source):
        if title_filter and title_filter not in title and title_filter not in section:
            continue
        if source == "shuowen" and len(keyword) == 1 and not section.startswith(f"{keyword} · "):
            continue
        text = re.sub(r"\s+", " ", body).strip()
        match = text.find(keyword)
        if match < 0:
            continue
        start, end = max(0, match - 42), min(len(text), match + len(keyword) + 66)
        record = metadata.get(path.as_posix(), {})
        yield {"title": title, "section": section, "edition": edition,
               "excerpt": ("…" if start else "") + text[start:end] + ("…" if end < len(text) else ""),
               "file": path.as_posix(), "source_url": record.get("url", ""), "license_note": record.get("license_note", "")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyword", help="原字形的连续字词，例如 守株")
    parser.add_argument("--title", default="", help="限定篇名或作品，如 韩非子")
    parser.add_argument("--source", choices=["all", "school", "lunyu", "gujilab", "ect", "shuowen"], default="all")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--json", action="store_true", help="输出结构化检索结果")
    args = parser.parse_args()
    keyword = args.keyword.strip()
    if not keyword or not 1 <= args.limit <= 60:
        parser.error("请给出关键词，结果数设在 1–60。")
    files = json_file(ROOT / "下载清单.json", {}).get("files", [])
    metadata = {record["file"]: record for record in files}
    matches = list(islice(search(keyword, args.title.strip(), args.source, metadata), args.limit))
    if args.json:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        return
    if not matches:
        print("未找到。可以试试繁体、简体或另一种写法。")
    for item in matches:
        print(f"{item['title']} / {item['section']}（{item['edition']}）\n{item['excerpt']}\n来源：{item['source_url'] or item['file']}\n")


if __name__ == "__main__":
    main()
