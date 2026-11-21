"""按诊断卷四组得分给出能力等级、主要缺口和下一步任务。

用法：
    python -B -X utf8 定级.py --scores 8,6,7,9
    python -B -X utf8 定级.py --l0 fail
    python -B -X utf8 定级.py --scores 9,9,8,9 --json
    python -B -X utf8 定级.py --scores 9,9,8,9 --exam-percent 85 --exam-minutes 35 --exam-reviewed
"""

import argparse
import json
import sys


PASS = 7

LEVELS = (
    {
        "id": "L0",
        "name": "认读起步",
        "focus": "朗读停顿、动作词、「之」的指代",
        "files": ("13-断句体系.md", "10-实词体系.md"),
        "task": "独立读《司马光》，说出人物、动作、结果三件事，停顿不出错。",
        "path": "03-路径-小学.md",
    },
    {
        "id": "L1",
        "name": "词义入门",
        "focus": "古今异义四类、通假三条线索、一词多义怎么定项",
        "files": ("10-实词体系.md", "11-虚词体系.md"),
        "task": "给一段小古文，解释 5 个加点词，答对至少 4 个，至少 3 个能说出依据。",
        "path": "03-路径-小学.md",
    },
    {
        "id": "L2",
        "name": "句法意识",
        "focus": "判断句、被动句、省略句、倒装句；18 个虚词各 2 种用法",
        "files": ("12-句式体系.md", "11-虚词体系.md"),
        "task": "用短文或四个句例辨认判断、被动、省略、倒装，补出省略成分并说通句意。",
        "path": "04-路径-初中.md",
    },
    {
        "id": "L3",
        "name": "翻译达标",
        "focus": "留删换调补贯六字诀、采分点意识、否定与范围词",
        "files": ("14-翻译体系.md", "12-句式体系.md"),
        "task": "译 150 字史传或论说，得分 80% 以上，能说清每处扣分原因。",
        "path": "04-路径-初中.md",
    },
    {
        "id": "L4",
        "name": "篇章分析",
        "focus": "层次划分、要点概括、人物评价、双材料比较、文化常识",
        "files": ("15-文化常识.md", "30-练习与讲评闭环.md"),
        "task": "给 300 字史传加两道题，概括准确，每个判断都能引原文。",
        "path": "05-路径-高中.md",
    },
    {
        "id": "L5",
        "name": "应试稳定",
        "focus": "断句、翻译、概括、赏析四类题型规范；时间分配与错因归因",
        "files": ("30-练习与讲评闭环.md",),
        "task": "限时 35 分钟做一套高考真题，85% 以上，错题能归因到具体动作。",
        "path": "05-路径-高中.md",
    },
)

GROUPS = ("词义", "句法", "翻译", "篇章")


def parse_scores(text):
    parts = [part.strip() for part in text.replace("，", ",").split(",") if part.strip()]
    if len(parts) != 4:
        raise ValueError("--scores 需要四个分数，依次是词义、句法、翻译、篇章，例如 8,6,7,9")
    scores = []
    for part in parts:
        value = float(part)
        if not 0 <= value <= 10:
            raise ValueError(f"分数须在 0 到 10 之间：{part}")
        scores.append(value)
    return scores


def decide(scores, l0_failed, exam_qualified=False):
    if l0_failed:
        return "L0"
    for index, score in enumerate(scores):
        if score < PASS:
            return LEVELS[index + 1]["id"]
    return "L5" if exam_qualified else "L4"


def profile(scores, start_group):
    """给出强项、弱项和一句画像。起点组和最低分组可能不是同一个。"""
    ranked = sorted(zip(GROUPS, scores), key=lambda item: item[1], reverse=True)
    strong = [name for name, score in ranked if score >= PASS]
    weak = [name for name, score in ranked if score < PASS]
    best = ranked[0]
    worst = ranked[-1]
    if len(weak) == 0:
        sentence = "四组都过线，可以直接进篇章与应试训练。"
    elif len(weak) >= 3:
        sentence = "多数板块低于及格线，建议回到本级路径慢走一轮，不要跳级。"
    elif start_group and start_group != worst[0]:
        sentence = (f"{best[0]}是强项；{worst[0]}分最低，但按顺序要先补{start_group}，"
                    f"过关后再补{worst[0]}。")
    else:
        sentence = f"{best[0]}是相对强项，{worst[0]}是最短的一块板，先补它。"
    return strong, weak, sentence


def build(scores, l0_failed, exam_qualified=False):
    level_id = decide(scores, l0_failed, exam_qualified)
    level_index = int(level_id[1:])
    level = LEVELS[level_index]
    start_group = GROUPS[level_index - 1] if 1 <= level_index <= 4 else None
    if l0_failed:
        strong, weak, sentence = [], [], "朗读观察未通过，先补停顿、复述和代词指代。"
    else:
        strong, weak, sentence = profile(scores, start_group)
    payload = {
        "level": level["id"],
        "name": level["name"],
        "focus": level["focus"],
        "task": level["task"],
        "files": list(level["files"]),
        "path": level["path"],
        "scores": dict(zip(GROUPS, scores)),
        "strong": strong,
        "weak": weak,
        "note": sentence,
    }
    if level_id == "L5":
        payload["note"] = "四组均已过线，教师已提交一套符合标准的限时真题记录。"
        payload["next"] = "进入 L5 训练，换真题连续观察得分、用时和错因是否稳定。"
    elif level_id == "L4" and not weak:
        payload["next"] = "先走 L4 路线；按真题得分、用时和错因复核结果判定是否进入 L5。"
    elif level["id"] == "L0":
        payload["next"] = "先做朗读与复述，不急着做题；每天读 3 遍同一篇短文。"
    else:
        payload["next"] = f"按 {level['path']} 的当前轮次走，完成上面的过关任务再升级。"
    return payload


def render(payload):
    scores = payload["scores"]
    line = "  ".join(f"{name} {scores[name]:g}" for name in GROUPS) if scores else "四组未测"
    files = "、".join(payload["files"])
    return "\n".join([
        "能力诊断结果",
        "=" * 32,
        f"分数：{line}",
        f"起点：{payload['level']}　{payload['name']}",
        f"主攻：{payload['focus']}",
        f"画像：{payload['note']}",
        "",
        f"过关任务：{payload['task']}",
        f"要读的文件：{files}",
        f"学习路径：{payload['path']}",
        "",
        f"下一步：{payload['next']}",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scores", help="四组得分，逗号分隔：词义,句法,翻译,篇章")
    parser.add_argument("--l0", choices=("pass", "fail"), default="pass", help="第 0 组朗读观察是否通过")
    parser.add_argument("--exam-percent", type=float, help="高考真题文言文部分的得分百分比，例如 85")
    parser.add_argument("--exam-minutes", type=float, help="本次真题实际完成用时，单位为分钟")
    parser.add_argument("--exam-reviewed", action="store_true", help="教师已核对每处失分对应的错因，或确认无失分")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if args.scores is None and args.l0 != "fail":
        parser.error("朗读观察通过后，请提供四组 --scores")
    try:
        scores = parse_scores(args.scores) if args.scores is not None else []
    except ValueError as error:
        parser.error(str(error))
    percent, minutes = args.exam_percent, args.exam_minutes
    if percent is not None or minutes is not None or args.exam_reviewed:
        if args.l0 == "fail" or percent is None or minutes is None:
            parser.error("录入 L5 真题证据需要通过朗读观察，并同时填写分数百分比和用时")
        if not 0 <= percent <= 100 or not 0 < minutes < float("inf"):
            parser.error("真题百分比须在 0 到 100 之间，用时须为正数")
    exam_qualified = percent is not None and percent >= 85 and minutes <= 35 and args.exam_reviewed

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    payload = build(scores, args.l0 == "fail", exam_qualified)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render(payload))


if __name__ == "__main__":
    main()
