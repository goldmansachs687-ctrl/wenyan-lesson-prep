"""生成篇目地图，复用课文查询的学制、底本及版次匹配。

主题线是人工归纳的，写在下面的常量里；表格部分从目录与正文数据自动生成，
重跑不会覆盖主题线。
"""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COURSE = ROOT / "文言文语料库" / "教学参考" / "统编课内"
TARGET = ROOT / "文言文知识体系" / "20-篇目地图.md"
CARDS = ROOT / ".agents" / "skills" / "wenyan-lesson-prep" / "references" / "classroom.json"
sys.path.insert(0, str(COURSE))
from 查课文 import lookup, normalize

GRADE_ORDER = {
    "三年级": 1, "四年级": 2, "五年级": 3, "六年级": 4,
    "七年级": 5, "八年级": 6, "九年级": 7, "高中": 8,
}
VOLUME_ORDER = {"上册": 1, "下册": 2, "必修上册": 3, "必修下册": 4,
                "选择性必修上册": 5, "选择性必修中册": 6, "选择性必修下册": 7}

THEMES = (
    ("寓言与哲理", (
        "守株待兔", "自相矛盾", "精卫填海", "愚公移山", "北冥有鱼",
        "庄子与惠子游于濠梁之上", "马说", "种树郭橐驼传", "五石之瓠",
    )),
    ("史传与人物", (
        "周亚夫军细柳", "陈涉世家", "屈原列传", "苏武传", "鸿门宴",
        "烛之武退秦师", "唐雎不辱使命", "邹忌讽齐王纳谏", "曹刿论战",
    )),
    ("写景与游记", (
        "三峡", "答谢中书书", "记承天寺夜游", "与朱元思书", "小石潭记",
        "桃花源记", "醉翁亭记", "岳阳楼记", "湖心亭看雪", "登泰山记",
        "石钟山记", "赤壁赋",
    )),
    ("论说与议论", (
        "论语十二章", "得道多助，失道寡助", "富贵不能淫", "生于忧患，死于安乐",
        "虽有嘉肴", "大道之行也", "师说", "劝学（节选）", "过秦论", "六国论",
        "谏太宗十思疏", "答司马谏议书", "五代史伶官传序",
    )),
    ("家书与赠序", (
        "诫子书", "送东阳马生序", "陈情表", "兰亭集序",
        "归去来兮辞并序", "项脊轩志", "与妻书",
    )),
    ("笔记与志怪", (
        "咏雪", "陈太丘与友期行", "狼", "穿井得一人", "杞人忧天",
        "卖油翁", "河中石兽", "活板", "促织",
    )),
    ("诸子与政论", (
        "子路、曾皙、冉有、公西华侍坐", "齐桓晋文之事", "庖丁解牛",
        "谏逐客书", "兼爱", "老子四章", "大学之道", "人皆有不忍人之心",
    )),
)


def append_rows(lines, rows, cards):
    current_grade = None
    for row in sorted(rows, key=lambda row: (GRADE_ORDER.get(row["grade"], 9),
                                             VOLUME_ORDER.get(row["volume"], 9), row["title"])):
        if row["grade"] != current_grade:
            current_grade = row["grade"]
            lines.extend(["", f"### {row['stage']}·{current_grade}" if current_grade != row["stage"] else f"### {current_grade}", "",
                          "| 篇目 | 册次 | 文体 | 正文字数 | 正文依据 | 已有课堂卡 |",
                          "| --- | --- | --- | --- | --- | --- |"])
        body = normalize(row.get("base_text", {}).get("text", ""))
        terms = dict.fromkeys(card["term"] for card in cards.get(row["title"], [])
                              if normalize(card.get("searchQuote") or card["quote"]) in body)
        covered = "、".join(terms) or "—"
        count = len(body)
        lines.append(f'| {row["title"]} | {row["volume"]} | {row.get("text_type") or "—"} '
                     f'| {count} | {row["text_status"]} | {covered} |')


def main():
    standard = lookup("", limit=1000, show_text=True)
    five_four = lookup("", limit=1000, show_text=True, school_system="五四")
    cards = {}
    for card in json.loads(CARDS.read_text(encoding="utf-8-sig")):
        cards.setdefault(card["title"], []).append(card)

    lines = [
        "# 篇目地图", "",
        f"共 {len(standard) + len(five_four)} 个文言文收录位置。相同篇目跨学制、册次或版次时分别计数。",
        "字数按所附底本计算，课堂篇幅以本册课文为准。共享底本需复核本册的选段、字形和标点。",
        "课堂卡按原句与当前底本匹配。同名篇目的不同选段分别核对，字形有异时可按考点另查。",
        "", "## 六三学制与高中",
    ]
    append_rows(lines, standard, cards)
    lines.extend(["", "## 五四学制"])
    append_rows(lines, five_four, cards)

    lines.extend(["", "## 七条主题线", "",
                  "同一主题跨学段组课，比按教材顺序重讲更省课时。每条线后面的数字是篇数。", ""])
    for name, titles in THEMES:
        lines.append(f"**{name}**（{len(titles)} 篇）")
        lines.append("")
        lines.append("、".join(f"《{title}》" for title in titles))
        lines.append("")

    lines.extend([
        "## 怎么用",
        "",
        "- **备一节课**：先在本表查到篇目和字数，判断课时；再按主题线找 1—2 篇同主题材料做迁移。",
        "- **组专题课**：直接用主题线，每条线汇总同主题篇目，可按待练能力选材料。",
        "- **考前回扣**：按「已有课堂卡」一栏，找还没练到的篇目；不要按教材顺序重讲。",
        "- **核对教材册次、印次或页码**：查看[六三和高中目录](../文言文语料库/教学参考/统编课内/课内目录.md)、[五四学制目录](../文言文语料库/教学参考/统编课内/五四学制课内目录.md)。",
        "",
        "本表由 `文言文知识体系/数据/生成篇目地图.py` 生成，改篇目后重跑即可。",
    ])

    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"已生成 {TARGET.relative_to(ROOT)}：{len(standard) + len(five_four)} 个位置，{len(THEMES)} 条主题线。")


if __name__ == "__main__":
    sys.exit(main())
