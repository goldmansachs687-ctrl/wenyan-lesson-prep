"""校验知识体系文档里的课内引文能否在正文底本中回查。

提取「引文·《篇目》」形式，去掉加粗标记和括注，按去标点的纯文本比对。
只报告找不到的句子，供人工核对；不修改任何文件。
"""

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "文言文语料库" / "教学参考" / "统编课内" / "正文.jsonl"
DOCS = sorted((ROOT / "文言文知识体系").glob("*.md"))

QUOTE = re.compile(r"([^｜|·\n]{2,60}?)·《([^》]{1,30})》")
EXERCISE = re.compile(r"\*\*\d+\.\*\*\s*(.+?)（《([^》]+)》）", re.S)
MARK = re.compile(r"\*\*|`")
PAREN = re.compile(r"（[^）]*）|\([^)]*\)")


def plain(text):
    return "".join(char for char in text if char.isalnum())


def quoted(raw):
    """行内引文可能写成「课内例：`原句`」，只取反引号里的部分。"""
    codes = re.findall(r"`([^`]+)`", raw)
    if codes:
        return codes[-1]
    return re.split(r"[:：]", PAREN.sub("", raw))[-1]


def load_corpus(path=CORPUS):
    texts = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            texts.setdefault(row.get("title", ""), "")
            texts[row.get("title", "")] += row.get("text", "")
    return {title: plain(body) for title, body in texts.items()}


def check_exercises(all_text):
    """题库学生版里「**N.** 原句（《篇目》）」形式的引文也要能回查。"""
    folder = ROOT / "文言文知识体系" / "练习" / "学生版"
    missing = []
    checked = 0
    for document in sorted(folder.glob("*.md")):
        for number, line in enumerate(document.read_text(encoding="utf-8-sig").splitlines(), 1):
            for match in EXERCISE.finditer(line):
                quote = plain(MARK.sub("", match.group(1)))
                if len(quote) < 6:
                    continue
                checked += 1
                if quote not in all_text:
                    missing.append((document.name, number, match.group(2).strip(), match.group(1).strip()))
    return checked, missing


def check_retest(corpus):
    """复测引文逐条核对到所标篇目，两种学制的底本都可用于复测。"""
    document = ROOT / "文言文知识体系" / "练习" / "学生版" / "分级复测.md"
    quotes = re.compile(r"^> (.+)（《([^》]+)》）$")
    missing = []
    checked = 0
    for number, line in enumerate(document.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.startswith("> "):
            continue
        match = quotes.fullmatch(line)
        if not match:
            missing.append((document.name, number, "出处待标", line))
            continue
        text, title = match.groups()
        checked += 1
        if plain(text) not in corpus.get(title, ""):
            missing.append((document.name, number, title, text))
    return checked, missing


def main():
    corpus = load_corpus()
    all_text = "".join(corpus.values())
    missing = []
    checked = 0
    for document in DOCS:
        for number, line in enumerate(document.read_text(encoding="utf-8-sig").splitlines(), 1):
            if "·《" not in line:
                continue
            for raw, title in QUOTE.findall(line):
                quote = plain(PAREN.sub("", MARK.sub("", quoted(raw))))
                if len(quote) < 3 or "课外" in raw or "课外" in line:
                    continue
                checked += 1
                if quote in all_text:
                    continue
                missing.append((document.name, number, title.strip(), raw.strip()))

    exercise_checked, exercise_missing = check_exercises(all_text)
    checked += exercise_checked
    missing.extend(exercise_missing)
    retest_checked, retest_missing = check_retest({**corpus, **load_corpus(CORPUS.with_name("正文-五四.jsonl"))})
    checked += retest_checked
    missing.extend(retest_missing)

    print(f"检查 {len(DOCS)} 份文档与题库，{checked} 条引文。")
    if not missing:
        print("全部可在正文底本中回查到。")
        return 0
    print(f"有 {len(missing)} 条未能回查，请人工核对（可能是课外例、节选差异或笔误）：")
    for name, number, title, raw in missing:
        print(f"  {name}:{number}　《{title}》　{raw}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
