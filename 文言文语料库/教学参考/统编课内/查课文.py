"""离线查询统编文言文篇目、册次和有出处的原文底本。"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import unicodedata


ROOT = Path(__file__).resolve().parent
CATALOGUES = ("义务教育.json", "高中.json")
FIVE_FOUR = "五四学制.json"
EXACT_GRADES = "一二三四五六七八九"
GRADE_ALIASES = {"初一": "七年级", "初二": "八年级", "初三": "九年级", **dict.fromkeys(("高一", "高二", "高三"), "高中")}
GRADE_FORM = re.compile(r"([一二三四五六七八九1-9])(?:年级)?(?:([上下])(?:册)?)?")


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return "".join(char for char in text if char.isalnum())


def period(grade):
    if grade == "高中":
        return grade
    if grade and grade[0] in EXACT_GRADES[:6]:
        return "小学"
    if grade and grade[0] in EXACT_GRADES[6:]:
        return "初中"
    return ""


def five_four_volumes():
    path = ROOT / FIVE_FOUR
    if path.is_file():
        yield from json.loads(path.read_text(encoding="utf-8-sig"))["coverage"]


def catalogue(school_system=""):
    if school_system == "五四":
        for book in five_four_volumes():
            grade = book["grade"]
            stage = "初中" if grade == "六年级" else period(grade)
            for lesson in book["lessons"]:
                yield {
                    "stage": stage,
                    "school_system": "五四",
                    "grade": grade,
                    "volume": book["volume"],
                    "editions": [book["verified_edition"]],
                    "source_urls": book["source_urls"][:1],
                    **lesson,
                }
        return
    for filename in CATALOGUES[:1] if school_system == "六三" else CATALOGUES:
        path = ROOT / filename
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            for row in data["entries"]:
                yield {"stage": period(row["grade"]), **row}


def volumes(school_system=""):
    if school_system == "五四":
        yield from five_four_volumes()
        return
    required = ROOT / CATALOGUES[0]
    secondary = ROOT / CATALOGUES[1]
    if required.is_file():
        data = json.loads(required.read_text(encoding="utf-8-sig"))
        yield from data.get("coverage", [])
    if school_system != "六三" and secondary.is_file():
        data = json.loads(secondary.read_text(encoding="utf-8-sig"))
        books = {}
        for row in data["entries"]:
            books.setdefault(row["volume"], row.get("source_urls", []))
        for volume, sources in books.items():
            yield {
                "grade": "高中", "volume": volume, "status": "已核国家智慧教育平台电子教材",
                "source_urls": sources[:1],
            }


def texts(filename="正文.jsonl"):
    records = {}
    path = ROOT / filename
    if path.is_file():
        with path.open(encoding="utf-8-sig") as stream:
            for line in stream:
                item = json.loads(line)
                records[(item.get("grade", ""), item["title"])] = item
    return records


def lookup(query, grade="", volume="", limit=12, show_text=False, match_body=False, edition="", school_system=""):
    word = normalize(query)
    grade = GRADE_ALIASES.get(grade.strip(), grade.strip())
    if match := GRADE_FORM.fullmatch(grade):
        year, term = match.groups()
        if year.isdecimal():
            year = EXACT_GRADES[int(year) - 1]
        grade = year + "年级"
        if term and not volume:
            volume = term + "册"
    if volume in {"上", "下", "必修上", "必修下", "选择性必修上", "选择性必修中", "选择性必修下"}:
        volume += "册"
    books = texts()
    specific_books = texts("正文-五四.jsonl") if school_system == "五四" else {}
    matches = []
    for entry in catalogue(school_system):
        if grade and grade not in {entry["grade"], entry["stage"]}:
            continue
        if volume and volume != entry["volume"]:
            continue
        if edition and not any(edition in value for value in entry.get("editions", [])):
            continue
        title = entry["title"]
        names = [title, *entry.get("aliases", [])]
        body_keys = [(level, name) for name in names for level in (entry["grade"], "")]
        specific = next((specific_books[key] for key in body_keys if key in specific_books), None)
        item = specific or next((books[key] for key in body_keys if key in books), None)
        if school_system == "五四" and item is None:
            other_grades = [body for (level, name), body in books.items()
                            if name == title and level != "高中"]
            if len(other_grades) == 1:
                item = other_grades[0]
        keys = [normalize(name) for name in names]
        if not word or word in keys:
            rank = 0
        elif any(word in key for key in keys):
            rank = 1
        elif match_body and item and word in normalize(item["text"]):
            rank = 2
        else:
            continue
        record = {**entry, "text_status": item["status"] if item else "正文待补"}
        if item:
            evidence = {key: value for key, value in item.items() if key != "text"}
            if school_system == "五四" and specific is None:
                evidence.pop("boundary_source_url", None)
                evidence["variant_note"] = "此处为共享古文底本。五四教材的选段、字形与标点以指定原册为准。"
                record["text_status"] = "共享底本参照"
            record["base_text"] = evidence
            if show_text:
                record["base_text"]["text"] = item["text"]
        matches.append((rank, record))
    matches.sort(key=lambda pair: pair[0])
    return [record for _, record in matches[:limit]]


def stats(school_system=""):
    rows = list(catalogue(school_system))
    bodies = texts("正文-五四.jsonl") if school_system == "五四" else texts()
    matches = list(lookup("", limit=len(rows), school_system=school_system))
    return {
        "placements": len(rows),
        "titles": len({row["title"] for row in rows}),
        "by_stage": dict(Counter(row["stage"] for row in rows)),
        "by_grade_and_volume": dict(Counter(f"{row['grade']}/{row['volume']}" for row in rows)),
        "volumes": list(volumes(school_system)),
        "text_status_by_placement": dict(Counter(row["text_status"] for row in matches)),
        "text_file_records": len(bodies),
        "open_text_gaps": sorted({row["title"] for row in matches if not row.get("base_text")}),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="", help="按篇名、别名查找")
    parser.add_argument("--grade", default="", help="小学、初中、高中、年级名或简写，如 八下")
    parser.add_argument("--volume", default="", help="如：上册、选择性必修下册")
    parser.add_argument("--edition", default="", help="筛选目录已标注的版次，如 修订前早期印次")
    parser.add_argument("--school-system", choices=("六三", "五四"), default="",
                        help="选择义务教育学制；默认保留六三学制与高中的查询范围")
    parser.add_argument("--list", action="store_true", help="列出本册或现有目录")
    parser.add_argument("--text", action="store_true", help="附有出处的离线底本正文")
    parser.add_argument("--match-body", action="store_true", help="额外按原字形匹配原文")
    parser.add_argument("--stats", action="store_true", help="打印篇目和底本覆盖量")
    parser.add_argument("--json", action="store_true", help="输出结构化数据")
    parser.add_argument("--limit", type=int, default=12, help="返回数目，1–200")
    args = parser.parse_args()
    if args.stats:
        print(json.dumps(stats(args.school_system), ensure_ascii=False, indent=2))
        return
    if not 1 <= args.limit <= 200 or (not normalize(args.query) and not args.list):
        parser.error("请提供篇名或使用 --list。结果数量应为 1–200。")
    limit = 200 if args.list and args.limit == 12 else args.limit
    rows = lookup(args.query, args.grade, args.volume, limit, args.text, args.match_body,
                  args.edition, args.school_system)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("暂无匹配。可用较短的篇名，或用 --list 查看册次。")
    for row in rows:
        system = f"{row['school_system']}学制 " if "school_system" in row else ""
        print(f"《{row['title']}》 {system}{row['grade']}·{row['volume']}｜{row['text_status']}")
        if row.get("page"):
            group = f" {row['group']}" if row.get("group") else ""
            print(f"教材第{row['lesson']}课{group}，参见第{row['page']}页｜{row['source_urls'][0]}")
        if row.get("note"):
            print(row["note"])
        if row.get("base_text"):
            base = row["base_text"]
            print(f"{base['edition']}｜{base['source_url']}")
            if base.get("locator"):
                print(f"原文位置 {base['locator']}")
            if base.get("variant_note"):
                print(f"版本提示 {base['variant_note']}")
            if base.get("boundary_source_url"):
                print(f"教材选段核对 {base['boundary_source_url']}")
            if args.text:
                print(base["text"])
        print()


if __name__ == "__main__":
    main()
