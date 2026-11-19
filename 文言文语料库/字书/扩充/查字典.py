"""离线查释义、古字书和字形。按字头或词条精确查找。"""

from __future__ import annotations

import argparse
from contextlib import closing
from itertools import zip_longest
import json
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parent
SOURCES = (
    {
        "id": "wiktionary",
        "name": "中文维基词典",
        "kind": "有文言引文的释义与明确标记的书面释义",
        "license": "CC BY-SA 4.0",
        "source_url": "https://zh.wiktionary.org/",
        "database": "维基文言词义.sqlite3",
    },
    {
        "id": "kangxi",
        "name": "康熙字典",
        "kind": "开放康熙字典校录的古字书原文",
        "license": "GPL-3.0（该 XML 仓库）",
        "source_url": "https://github.com/ksanaforge/kangxizidian",
        "database": "康熙字典.sqlite3",
    },
    {
        "id": "shuowen",
        "name": "说文解字",
        "kind": "Shuowen.org 整理的说文原文",
        "license": "Apache-2.0",
        "source_url": "https://github.com/shuowenjiezi/shuowen",
        "database": "说文解字.sqlite3",
    },
)
QUERY_NOTES = (
    "古字书释文保留原字和书证。字头命中是查读线索，具体语境义以本课原句和采分点为准。",
    "「有文言引文」表示维基词典将该义项与文言引文关联；「书面语」是原词典使用标签。",
    "「源数据异体」为该来源记录的字形关系，「OpenCC 简繁候选」存在一对多，应看返回的原字头。",
    "「字书核对候选」用于源索引缺录的字头关系，返回相应字书记录及出处。",
)
MATCH_TYPES = (
    ("exact", "原字头"),
    ("source_variant", "源数据异体"),
    ("simplified_variant", "OpenCC 简繁候选"),
    ("reviewed_variant", "字书核对候选"),
)
# 《康熙字典》手部「擧」条明确记为「舉本字」。
REVIEWED_VARIANTS = {"举": ("擧",), "舉": ("擧",)}


def simplified_candidates(query, root):
    if len(query) != 1:
        return ()
    dictionary = root / "OpenCC-STCharacters.txt"
    if not dictionary.is_file():
        return ()
    with dictionary.open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith(query + "\t"):
                return tuple(word for word in line.split()[1:] if word != query)
    return ()


def source_entries(connection, query, variants, source, limit, max_chars):
    # The indexed first two queries preserve a distinction between exact and
    # variant spellings. OpenCC candidates are alternate heads, not merged.
    queries = [
        (0, "SELECT * FROM entries WHERE headword = ? ORDER BY priority, id LIMIT ?", (query, limit)),
        (
            1, "SELECT entries.* FROM aliases JOIN entries ON entries.id = aliases.entry_id "
            "WHERE aliases.alias = ? ORDER BY entries.priority, entries.id LIMIT ?",
            (query, limit),
        ),
    ]
    for rank, candidates in enumerate((variants, REVIEWED_VARIANTS.get(query, ())), start=2):
        if not candidates:
            continue
        placeholders = ", ".join("?" for _ in candidates)
        queries.append((
            rank,
            f"SELECT * FROM entries WHERE headword IN ({placeholders}) ORDER BY priority, id LIMIT ?",
            (*candidates, limit),
        ))
    matched = set()
    for rank, statement, parameters in queries:
        for row in connection.execute(statement, parameters):
            if row["id"] in matched:
                continue
            matched.add(row["id"])
            definition = row["definition"]
            if len(definition) > max_chars:
                definition = definition[:max_chars].rstrip() + "…"
            yield rank, {
                "headword": row["headword"],
                "source": source["name"],
                "source_id": source["id"],
                "definition": definition,
                "gloss": definition,
                "language": row["language"],
                "labels": json.loads(row["labels"]),
                "source_url": row["source_url"],
                "match": MATCH_TYPES[rank][0],
                "match_label": MATCH_TYPES[rank][1],
                "locator": row["locator"],
                "license": source["license"],
                "part_of_speech": row["part_of_speech"],
                "truncated": len(row["definition"]) > max_chars,
            }


def lookup(query="", limit=8, source_id=None, max_chars=2200, root=ROOT):
    """Return testable structured results and source metadata, without writes."""
    query = query.strip()
    variants = simplified_candidates(query, root)
    sources = []
    by_match = [[] for _ in MATCH_TYPES]
    for source in SOURCES:
        if source_id and source["id"] != source_id:
            continue
        database = root / source["database"]
        item = {**source, "available": database.is_file()}
        sources.append(item)
        if not item["available"]:
            continue
        try:
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                db.row_factory = sqlite3.Row
                metadata = db.execute("SELECT document FROM provenance").fetchone()
                if metadata is None:
                    raise ValueError("缺少来源信息")
                groups = [[] for _ in MATCH_TYPES]
                if query:
                    for rank, row in source_entries(db, query, variants, source, limit, max_chars):
                        groups[rank].append(row)
                item.update(json.loads(metadata[0]))
                for collection, rows in zip(by_match, groups):
                    collection.append(rows)
        except (sqlite3.Error, OSError, ValueError) as error:
            item.update(available=False, error=str(error))
    results = []
    for collection in by_match:
        for batch in zip_longest(*collection):
            results.extend(row for row in batch if row is not None)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return {"query": query, "results": results[:limit], "sources": sources, "notes": list(QUERY_NOTES)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", help="字或词，例如「顾」「俨然」")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--limit", type=int, default=8, help="最大条数，默认 8")
    parser.add_argument("--max-chars", type=int, default=2200, help="每条释文最多显示的字符数")
    parser.add_argument("--stats", action="store_true", help="仅显示本地来源和统计量")
    parser.add_argument("--source", choices=[source["id"] for source in SOURCES])
    args = parser.parse_args()
    if not args.stats and (not args.query or not 1 <= len(args.query.strip()) <= 32):
        parser.error("请输入 1 到 32 个字符的字头或词条，或使用 --stats。")
    if not 1 <= args.limit <= 100:
        parser.error("--limit 须在 1 到 100 之间。")
    if not 1 <= args.max_chars <= 20000:
        parser.error("--max-chars 须在 1 到 20000 之间。")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    results = lookup("" if args.stats else args.query, args.limit, args.source, args.max_chars)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.stats:
        for source in results["sources"]:
            if source["available"]:
                print(f"{source['name']}  {source['headwords']} 个字头/词条，{source['records']} 条索引记录")
            else:
                print(f"{source['name']}  本地索引不可用")
    else:
        for entry in results["results"]:
            print(f"\n{entry['headword']}｜{entry['source']}｜{entry['match_label']}")
            print(f"{'、'.join(entry['labels'])}｜{entry['locator']}")
            print(entry["definition"])
            print(entry["source_url"])
        if not results["results"]:
            print(f"本地字书没有找到「{args.query}」。")
    return 0 if any(source["available"] for source in results["sources"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
