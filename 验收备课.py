"""检查公开备课包的课文、辞书、分级题库与教师资料检索。"""

import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
TEACHER = ROOT / "文言文教学" / "教师备课资料"
COURSE = ROOT / "文言文语料库" / "教学参考" / "统编课内"
DICTIONARY = ROOT / "文言文语料库" / "字书" / "扩充"
SKILL_LOOKUP = ROOT / ".agents" / "skills" / "wenyan-lesson-prep" / "scripts" / "lookup.py"


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def read(path):
    return path.read_text(encoding="utf-8-sig")


def json_command(script, *args, explicit_json=True):
    result = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(script), *args, *(("--json",) if explicit_json else ())],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )
    if result.returncode:
        lines = (result.stderr or result.stdout).splitlines()
        raise ValueError(f"{script.name} 退出码 {result.returncode}，" + (lines[-1] if lines else "没有输出"))
    return json.loads(result.stdout)


def project_file(relative, directory, allowed):
    require(isinstance(relative, str) and relative, "缺少来源路径")
    candidate = Path(relative)
    require(not candidate.is_absolute(), f"应使用项目相对路径 {relative}")
    path = (directory / candidate).resolve()
    require(path.is_relative_to(allowed.resolve()) and path.is_file(), f"找不到预期文件 {relative}")
    return path


def secure_url(address):
    return isinstance(address, str) and (parsed := urlsplit(address)).scheme == "https" and bool(parsed.netloc)


def key(text):
    return "".join(char for char in text if char.isalnum())


def check_curriculum_catalogue():
    require(not COURSE.resolve().is_relative_to((TEACHER / "原始资料").resolve()), "统编课内资料应和教师原稿分开")
    basic = json.loads(read(COURSE / "义务教育.json"))
    senior = json.loads(read(COURSE / "高中.json"))
    expected = {(f"{year}年级", volume) for year in "一二三四五六七八九" for volume in ("上册", "下册")}
    locations = {(row["grade"], row["volume"]) for row in basic["coverage"]}
    require(len(basic["coverage"]) == 18 and locations == expected, "义务教育目录应逐一覆盖一至九年级 18 册")
    for proof in basic["coverage"]:
        require(any(map(secure_url, proof["source_urls"]))
                and re.fullmatch(r"[0-9a-fA-F]{64}", proof["verified_pdf_sha256"]),
                f"{proof['grade']}{proof['volume']}缺少教材出处或核对校验值")
    senior_volumes = {"必修上册", "必修下册", "选择性必修上册", "选择性必修中册", "选择性必修下册"}
    proof_volumes = {row["volume"] for row in senior["sources"] if row.get("volume") and secure_url(row.get("url"))}
    require({row["volume"] for row in senior["entries"]} == senior_volumes == proof_volumes,
            "高中文言目录及电子教材出处须覆盖必修与选择性必修 5 册")
    for document in (basic, senior):
        require(document["entries"] and all(any(map(secure_url, row["source_urls"])) for row in document["entries"]),
                "有课文条目缺少可回查出处")
    return f"义务教育 18 册和高中 5 册各有核验依据，共 {len(basic['entries']) + len(senior['entries'])} 条篇目位置"


def require_corrected_text(rows):
    def get(grade, volume, title):
        matches = [row for row in rows if (row["grade"], row["volume"], row["title"]) == (grade, volume, title)]
        require(len(matches) == 1, f"{grade}{volume}《{title}》验收需要一条指定版本底本")
        return key(matches[0]["base_text"]["text"])

    body = get("八年级", "下册", "北冥有鱼")
    require(not any(phrase in body for phrase in ("且夫水之积", "且夫水之積")), "八下《北冥有鱼》混入「且夫水之积」")
    require(body.endswith(("亦若是则已矣", "亦若是則已矣")), "八下《北冥有鱼》课内选段应止于「亦若是则已矣」")

    body = get("四年级", "上册", "精卫填海")
    require(not any(phrase in body for phrase in ("发鸠", "發鳩")), "四上《精卫填海》混入「发鸠」")
    require(body.startswith("炎帝之少女"), "四上《精卫填海》课内选段应从「炎帝之少女」起")

    body = get("高中", "选择性必修下册", "种树郭橐驼传")
    require(not any(phrase in body for phrase in ("病瘘", "病瘻")), "高中《种树郭橐驼传》混入误字「病瘘」")
    require(any(phrase in body for phrase in ("病偻", "病僂")), "高中《种树郭橐驼传》应保留「病偻」")

    body = get("高中", "选择性必修下册", "兰亭集序")
    require("一作" not in body, "高中《兰亭集序》正文混入「一作」校勘夹注")
    require(any(phrase in body for phrase in ("少长咸集", "少長咸集")), "高中《兰亭集序》缺「少长咸集」")

    for volume in ("上册", "下册"):
        body = get("九年级", volume, "邹忌讽齐王纳谏")
        require("一作" not in body, f"九年级{volume}《邹忌讽齐王纳谏》正文混入「一作」校勘夹注")

    body = get("六年级", "上册", "曹冲称象")
    require(any(phrase in body for phrase in ("邓哀王", "鄧哀王")), "六上《曹冲称象》缺「邓哀王」")
    require(any(phrase in body for phrase in ("时孙权", "時孫權")), "六上《曹冲称象》缺「时孙权」")


def check_curriculum_text():
    require((COURSE / "正文.jsonl").is_file(), "统编课内缺少「正文.jsonl」，目前无法验收选章正文")
    script = COURSE / "查课文.py"
    title = "论语十二章"
    versions = []
    for grade, volume, anchors in (
        ("七年级", "上册", (("学而时习之", "學而時習之"), ("温故而知新", "溫故而知新"))),
        ("高中", "选择性必修上册", (("君子食无求饱", "君子食無求飽"), ("朝闻道", "朝聞道"))),
    ):
        result = json_command(script, title, "--grade", grade, "--text")
        matches = [row for row in result if row["title"] == title and row["grade"] == grade and row["volume"] == volume]
        require(len(matches) == 1, f"{grade}{volume}的同名《论语》未能独立定位")
        base = matches[0].get("base_text") or {}
        body = key(base.get("text", ""))
        require(body and base.get("edition") and secure_url(base.get("source_url")),
                f"{grade}{volume}《论语》缺正文、底本或出处")
        require(all(any(anchor in body for anchor in group) for group in anchors),
                f"{grade}{volume}《论语》缺本册选章首句")
        versions.append((body, anchors))
    for own, other in ((0, 1), (1, 0)):
        require(not any(anchor in versions[own][0] for group in versions[other][1] for anchor in group),
                "七年级和高中《论语》正文中混入对方的选章")
    rows = json_command(script, "--list", "--text", "--limit", "200")
    stats = json_command(script, "--stats")
    require(len(rows) == stats["placements"], f"只能查到 {len(rows)} 个位置，目录实有 {stats['placements']} 个")
    missing = [
        f"{row['grade']}{row['volume']}《{row['title']}》"
        for row in rows
        if not (base := row.get("base_text"))
        or not key(base.get("text", ""))
        or not base.get("edition")
        or not secure_url(base.get("source_url"))
    ]
    require(not missing, f"{len(missing)} 个篇目位置缺正文或出处，例如 {'、'.join(missing[:3])}")

    incipits = {
        "琵琶行并序·小序": ("浔阳江头夜送客", "潯陽江頭夜送客"),
        "燕歌行并序·小序": ("汉家烟尘在东北", "漢家煙塵在東北"),
        "孔雀东南飞并序·小序": ("孔雀东南飞五里一徘徊", "孔雀東南飛五里一徘徊"),
        "扬州慢（淮左名都）·小序": ("淮左名都竹西佳处", "淮左名都竹西佳處"),
    }
    prefaces = {row["title"]: row for row in rows if row["grade"] == "高中" and row["text_type"] == "文言小序"}
    require(incipits.keys() <= prefaces.keys(), "未齐备四篇高中文言小序")
    for title, poem_starts in incipits.items():
        row = prefaces[title]
        preface = key(row["base_text"]["text"])
        boundaries = row["parts"][0]
        require(preface.startswith(key(boundaries["start"])) and preface.endswith(key(boundaries["end"])),
                f"《{title}》的小序起止与目录记录不同")
        require(not any(start in preface for start in poem_starts), f"《{title}》混入诗体正文")
    require_corrected_text(rows)
    return f"{len(rows)} 个位置均有正文及出处，初高中《论语》选章各自独立，四篇小序起止与六篇勘误检查通过"


def check_dictionary():
    script = DICTIONARY / "查字典.py"
    examples = (
        ("顾", "kangxi", "顧", "simplified_variant", "古字书原文", "迴首"),
        ("俨然", "wiktionary", "儼然", "source_variant", "书面语", "整齊"),
        ("之", "wiktionary", "之", "exact", "有文言引文", "往"),
    )
    for query, source, headword, match, label, evidence in examples:
        payload = json_command(script, query, "--limit", "20")
        hit = next((row for row in payload["results"] if row["source_id"] == source and row["headword"] == headword
                    and row["match"] == match and label in row["labels"] and evidence in row["definition"]), None)
        require(hit and all(hit.get(field) for field in ("locator", "license")) and secure_url(hit.get("source_url")),
                f"「{query}」缺预期释义、匹配方式或出处")
        if query == "之":
            require("书证：" in hit["locator"] and {row["source_id"] for row in payload["results"]} >= {
                "kangxi", "shuowen", "wiktionary",
            }, "查「之」时三路来源或文言书证不完整")
    return "「顾」「俨然」「之」可离线查到简繁、释义及原始出处"


def check_skill_lookup():
    course = json_command(SKILL_LOOKUP, "论语十二章", "--course", "--grade", "高中", "--text", explicit_json=False)
    require(any(row["grade"] == "高中" and row["volume"] == "选择性必修上册"
                and "君子食无求饱" in key(row.get("base_text", {}).get("text", ""))
                and secure_url(row["base_text"].get("source_url")) for row in course),
            "Skill 课内模式未返回指定学段的底本及出处")
    dictionary = json_command(SKILL_LOOKUP, "顾", "--dictionary", "--limit", "6", explicit_json=False)
    require(any(row["headword"] == "顧" and row["match"] == "simplified_variant"
                and secure_url(row["source_url"]) for row in dictionary["results"]),
            "Skill 字典模式未返回原字形、简繁关系及出处")
    classroom = json_command(SKILL_LOOKUP, "所以然", "--title", "关尹子教射",
                             "--category", "实词", explicit_json=False)
    require(any(row["title"] == "关尹子教射" and secure_url(row["source"])
                and "缘由" in row["meaning"] for row in classroom["classroom"]),
            "Skill 未能按词、篇目和类目联查五四学制课堂卡")
    return "Skill 的课内、辞书和课堂卡查询可以找回原句、字形及出处"


def check_five_four():
    script = COURSE / "查课文.py"
    system = ("--school-system", "五四")
    stats = json_command(script, "--stats", *system)
    expected = {(f"{year}年级", term) for year in "一二三四五六七八九" for term in ("上册", "下册")}
    actual = {(row["grade"], row["volume"]) for row in stats["volumes"]}
    require(actual == expected and len(stats["volumes"]) == len(expected),
            "五四学制的册次不齐或有重复")
    require(stats["placements"] == 57 and not stats["open_text_gaps"],
            "五四学制的 57 个课文收录位置未齐备正文参照")
    rows = json_command(SKILL_LOOKUP, "关尹子教射", "--course",
                        "--grade", "六年级", "--text", *system, explicit_json=False)
    require(len(rows) == 1 and rows[0]["school_system"] == "五四" and rows[0]["stage"] == "初中"
            and rows[0]["page"] == 47 and "察其所以然" in rows[0]["base_text"]["text"],
            "五四六下《关尹子教射》缺正确课页或离线正文")
    comparison = json_command(script, "两小儿辩日", "--grade", "六年级", *system)
    require(len(comparison) == 1 and comparison[0]["volume"] == "上册"
            and comparison[0]["text_status"] == "共享底本参照"
            and "boundary_source_url" not in comparison[0]["base_text"],
            "五四六上同名条目错误沿用了六三的教材选段链接")
    require(not json_command(script, "关尹子教射", "--grade", "六年级"),
            "默认六三目录混入了五四专属篇目")
    return "18 册、57 个收录位置有底本，验证学制分流、选段证据与六年级学段"


def check_guide_links():
    documents = [ROOT / "README.md", ROOT / "开始使用.md", SKILL_LOOKUP.parent.parent / "SKILL.md"]
    documents.extend(sorted((ROOT / "文言文知识体系").rglob("*.md")))
    links = 0
    pattern = re.compile(r"\[[^\]\n]+\]\(\s*(?:<([^>\n]+)>|([^\s)]+))\s*\)")
    for document in documents:
        for bracketed, bare in pattern.findall(read(document)):
            parsed = urlsplit(bracketed or bare)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (document.parent / unquote(parsed.path)).resolve()
            require(target.is_relative_to(ROOT) and target.exists(),
                    f"{document.relative_to(ROOT)} 的相对链接无法打开：{parsed.path}")
            links += 1
    return f"公开入口和知识体系中的 {links} 个相对链接可打开"


def check_exercises():
    """检查分级题库齐全、学生版不泄题、题量完整。"""
    base = ROOT / "文言文知识体系" / "练习"
    levels = (("L0-认读", 8), ("L1-词义", 12), ("L2-句法", 12), ("L3-翻译", 10), ("L4-篇章", 8), ("L5-应试", 5))
    require((base / "README.md").is_file(), "题库缺少说明文件")
    require((ROOT / "文言文知识体系" / "验证" / "黄金备课用例.md").is_file(), "缺少黄金备课用例")
    require((ROOT / "文言文知识体系" / "从这里开始.md").is_file(), "缺少总入口")
    require((ROOT / "文言文知识体系" / "讲解范例" / "狼-名词作状语-15分钟.md").is_file(), "缺少讲解范例")
    total = 0
    for name, expected in levels:
        student = base / "学生版" / f"{name}.md"
        teacher = base / "教师版" / f"{name}-答案.md"
        require(student.is_file() and teacher.is_file(), f"{name} 缺少学生版或教师版")
        text = read(student)
        for word in ("参考答案", "采分点", "错因预判", "建议采分", "得分："):
            require(word not in text, f"{name} 学生版出现「{word}」")
        numbers = re.findall(r"^\*\*(\d+)\.\*\*", text, flags=re.MULTILINE)
        require(len(numbers) == expected, f"{name} 学生版应有 {expected} 题，实际 {len(numbers)}")
        require(numbers == [str(i) for i in range(1, expected + 1)], f"{name} 学生版题号不连续")
        total += expected
    packs = ("L0-认读包", "L1-词义包", "L2-句法包", "L3-翻译包", "L4-篇章包", "L5-应试包")
    sections = ("过关任务", "本级知识清单", "必读章节", "必练", "检测", "常见卡点")
    for name in packs:
        text = read(ROOT / "文言文知识体系" / "分级" / f"{name}.md")
        for section in sections:
            require(f"## {section}" in text, f"{name} 缺少「{section}」小节")
        require(text.count("- [ ]") >= 8, f"{name} 知识清单少于 8 项")
    retest = read(base / "学生版" / "分级复测.md")
    answers = read(base / "教师版" / "分级复测-答案.md")
    for document in (retest, answers):
        require(re.findall(r"^## (L[0-5]) ", document, flags=re.MULTILINE)
                == [f"L{level}" for level in range(6)], "复测未逐级提供相应任务或答案")
    require("参考答案" not in retest and "采分点" not in retest, "复测学生版出现答案或采分点")
    return (f"L0—L5 共 {total} 题，另有六级独立复测，学生版与教师版分开，学生版无答案与采分点；"
            f"6 份分级学习包结构完整；黄金备课用例、讲解范例、总入口在位")


def check_knowledge_system():
    """检查知识体系的文件完整性、引文可回查、例句覆盖与定级脚本。"""
    base = ROOT / "文言文知识体系"
    required = (
        "00-总纲.md", "01-能力分级标准.md", "02-诊断与定级.md",
        "03-路径-小学.md", "04-路径-初中.md", "05-路径-高中.md",
        "10-实词体系.md", "11-虚词体系.md", "12-句式体系.md",
        "13-断句体系.md", "14-翻译体系.md", "15-文化常识.md",
        "16-阅读方法.md", "17-文体读法.md",
        "20-篇目地图.md", "30-练习与讲评闭环.md", "40-教师手册.md", "41-学生手册.md",
        "诊断/诊断卷.md", "诊断/诊断答案.md", "诊断/定级.py",
        "分级/README.md", "分级/L0-认读包.md", "分级/L1-词义包.md",
        "分级/L2-句法包.md", "分级/L3-翻译包.md", "分级/L4-篇章包.md", "分级/L5-应试包.md",
    )
    missing = [name for name in required if not (base / name).is_file()]
    require(not missing, f"知识体系缺少 {len(missing)} 份文件，例如 {missing[0] if missing else ''}")

    verify = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", str(base / "数据" / "校验引文.py")],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    require(verify.returncode == 0,
            "知识体系引文未能全部回查：" + (verify.stdout or verify.stderr).strip().splitlines()[-1])

    library = json.loads(read(base / "数据" / "虚词例句.json"))
    require(len(library["chars"]) == 18 and all(library["index"].get(char) for char in library["chars"]),
            "虚词例句库未覆盖 18 个虚词")

    grading = base / "诊断" / "定级.py"
    scenarios = (
        ("L0", "--l0", "fail"),
        ("L1", "--scores", "6,9,9,9"),
        ("L2", "--scores", "8,6,7,9"),
        ("L3", "--scores", "8,7,6,9"),
        ("L4", "--scores", "9,7,7,6"),
        ("L4", "--scores", "7,7,7,7"),
        ("L4", "--scores", "7,7,7,7", "--exam-percent", "84.9", "--exam-minutes", "35", "--exam-reviewed"),
        ("L4", "--scores", "7,7,7,7", "--exam-percent", "85", "--exam-minutes", "35.1", "--exam-reviewed"),
        ("L4", "--scores", "7,7,7,7", "--exam-percent", "85", "--exam-minutes", "35"),
        ("L5", "--scores", "7,7,7,7", "--exam-percent", "85", "--exam-minutes", "35", "--exam-reviewed"),
    )
    for level, *arguments in scenarios:
        grade = json_command(grading, *arguments)
        require(grade["level"] == level, f"定级 {arguments} 应为 {level}，实际为 {grade['level']}")
        if level == "L0":
            require(not grade["scores"], "L0 未作答时应保留空分数")

    map_text = read(base / "20-篇目地图.md")
    standard, five_four = map_text.split("## 五四学制", 1)
    placement = r"^\| [^|]+ \| [^|]+ \| [^|]+ \| [1-9]\d* \|"
    counts = [len(re.findall(placement, segment, flags=re.MULTILINE)) for segment in (standard, five_four)]
    require(counts == [96, 57] and "正文待补" not in map_text, f"篇目地图应覆盖 96 + 57 个有底本的位置，实际为 {counts}")

    cards = json.loads(read(ROOT / ".agents" / "skills" / "wenyan-lesson-prep" / "references" / "classroom.json"))
    require(all(card.get("title") for card in cards), "有课堂卡缺少关联篇目")
    return (f"{len(required)} 份体系与分级文件齐全，引文可回查，18 个虚词例句可用，"
            f"定级脚本覆盖 L0—L5 及真题门槛，篇目地图 153 个位置，{len(cards)} 张课堂卡有关联篇目")


def check_teacher_navigation():
    with TemporaryDirectory() as directory:
        sandbox = Path(directory)
        originals = sandbox / "原始资料"
        originals.mkdir()
        (originals / "司马光.doc").write_bytes(b"test fixture, format is not parsed")
        (originals / "课堂笔记.md").write_text("# 守株待兔\n学生先圈出动作词。\n", encoding="utf-8")
        subprocess.run([sys.executable, "-B", "-X", "utf8", str(TEACHER / "生成原稿索引.py"),
                        "--root", str(sandbox)], cwd=ROOT, check=True, capture_output=True, timeout=20)
        index = sandbox / "索引"
        records = json.loads(read(index / "原稿索引.json"))["records"]
        legacy = next(row for row in records if row["kind"] == "doc")
        require(legacy["extract"] is None and legacy["status"] != "ok", "旧 Word 应只编目，不提供正文")
        generate = runpy.run_path(str(TEACHER / "生成篇目导航.py"))["generate"]
        generate.__globals__.update(ROOT=sandbox, INDEX=index)
        with redirect_stdout(StringIO()):
            generate()
        result = read(index / "按篇目找老师资料.md")
        require("### 司马光" in result and "### 守株待兔" in result and "摘录第" in result,
                "教案索引未同时生成旧 Word 题名和常规资料摘录入口")
    return "使用临时资料验证旧 Word 编目、普通笔记摘录和跨篇目导航"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="输出结构化验收结果")
    args = parser.parse_args()
    checks = (
        ("统编目录", check_curriculum_catalogue), ("课内底本", check_curriculum_text),
        ("五四学制", check_five_four), ("文言字典", check_dictionary),
        ("知识体系", check_knowledge_system), ("分级题库", check_exercises),
        ("Skill 查询入口", check_skill_lookup), ("公开资料链接", check_guide_links),
        ("教师资料导航", check_teacher_navigation),
    )
    results = []
    for name, check in checks:
        try:
            results.append({"name": name, "passed": True, "detail": check()})
        except (OSError, ValueError, KeyError, IndexError, TypeError, StopIteration,
                subprocess.SubprocessError) as error:
            detail = " ".join(str(error).split())[:240]
            results.append({"name": name, "passed": False, "detail": detail})
    passed = sum(row["passed"] for row in results)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.json:
        print(json.dumps({"passed": passed, "total": len(results), "checks": results}, ensure_ascii=False, indent=2))
    else:
        for row in results:
            print(f"{'通过' if row['passed'] else '未通过'}｜{row['name']}｜{row['detail']}")
        print(f"共通过 {passed}/{len(results)} 项。")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
