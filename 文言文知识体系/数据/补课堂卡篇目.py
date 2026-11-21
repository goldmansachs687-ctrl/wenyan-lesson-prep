"""给课堂知识卡补「关联篇目」字段，便于按篇目反查考点。

映射按卡片 id 固定，重复运行结果一致。只补 title 字段，不改动原有内容。
"""

import json
import sys
from pathlib import Path


CARDS = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "wenyan-lesson-prep" / "references" / "classroom.json"

TITLES = {
    "R01": "守株待兔", "R02": "论语十二章", "R03": "桃花源记", "R04": "守株待兔",
    "R05": "论语十二章", "R06": "论语十二章", "R07": "论语十二章", "R08": "狼",
    "R09": "岳阳楼记", "R10": "论语十二章", "R11": "论语十二章", "R12": "愚公移山",
    "R13": "桃花源记", "R14": "桃花源记", "R15": "出师表", "R16": "狼",
    "R17": "邹忌讽齐王纳谏", "R18": "送东阳马生序", "R19": "陋室铭", "R20": "出师表",
    "R21": "守株待兔", "R22": "曹刿论战", "R23": "论语十二章", "R24": "陋室铭",
    "R25": "守株待兔", "R26": "桃花源记", "R27": "三峡", "R28": "爱莲说",
    "R29": "生于忧患，死于安乐", "R30": "陈涉世家", "R31": "曹刿论战", "R32": "岳阳楼记",
    "R33": "陈太丘与友期行", "R34": "出师表", "R35": "劝学（节选）", "R36": "劝学（节选）",
}


def main():
    rows = json.loads(CARDS.read_text(encoding="utf-8-sig"))
    missing = []
    for row in rows:
        title = TITLES.get(row.get("id"))
        if title:
            row["title"] = title
        elif not row.get("title"):
            missing.append(row.get("id"))
    if missing:
        sys.exit(f"以下卡片没有关联篇目：{missing}")
    CARDS.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已为 {len(rows)} 张卡片补上关联篇目，覆盖 {len(set(TITLES.values()))} 篇。")


if __name__ == "__main__":
    main()
