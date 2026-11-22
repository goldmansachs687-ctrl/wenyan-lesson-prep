"""Download pinned, publicly released corpus files and record local provenance."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent
LIMIT = 65 * 1024**2


def pinned(repo, revision, files):
    return {name: f"https://raw.githubusercontent.com/{repo}/{revision}/{quote(name)}" for name in files}


BENCH_TASKS = ["translate", "punctuate", "char_gloss", "idiom_source", "fill_in", "compress"]
EARLY_TEXTS = ["KR1h0004", "KR1h0001", "KR3c0005", "KR3a0002", "KR5c0126", "KR2e0003", "KR3j0002", "KR3j0009", "KR5c0124", "KR1j0002"]
DATASETS = {
    "原文/gujilab": ("CC0-1.0 according to publisher; upstream attribution/rights apply", "https://huggingface.co/datasets/gujilab/chinese-classical-corpus", {
        file: "https://huggingface.co/datasets/gujilab/chinese-classical-corpus/resolve/1979f15b4b749b3601fd9ee3e4111a725c079439/" + file
        for file in ("README.md", "corpus.jsonl")
    }),
    "原文/ect-krp": ("CC-BY-SA-4.0", "https://github.com/direct-phonology/ect-krp", pinned(
        "direct-phonology/ect-krp", "b28fab8f54b0e3ec3ca97cc2baa8caecfe71259f",
        ["LICENSE", "README.md", *(f"jsonl/{key}.jsonl" for key in EARLY_TEXTS)],
    )),
    "原文/chinese-poetry": ("MIT repository; underlying ancient text, verify editorial sources", "https://github.com/chinese-poetry/chinese-poetry", pinned(
        "chinese-poetry/chinese-poetry", "b8594f81a89752241442f2ce267d6f66f96704ee",
        ["LICENSE", "论语/README.md", "论语/lunyu.json", "蒙学/guwenguanzhi.json"],
    )),
    "教学参考/初中古诗文旧版": ("CC BY-SA 4.0。按旧版教材 OCR 整理，使用时核对字形和选段。", "https://github.com/tangyuan0821/Junior-Middle-School-poetry", pinned(
        "tangyuan0821/Junior-Middle-School-poetry", "b4566586ed88bd8916b458e5a60e2100243a1428",
        ["LICENSE", "poetry.json"],
    )),
    "教学参考/reciting-us": ("MIT for project-authored text; ancient originals public domain per PROVENANCE.md", "https://github.com/HelloZWH-0620/Reciting-us/blob/main/PROVENANCE.md", pinned(
        "HelloZWH-0620/Reciting-us", "40a00d0cd9bfd3c530770d72efbdae1a4c61105f",
        ["LICENSE", "PROVENANCE.md", "RecitingUsApp/web/config/articles.json"],
    )),
    "教学参考/taotao": ("MIT for the repository-authored skill and guides; exam excerpts have separate provenance", "https://github.com/ichangting/taotao-skills/tree/main/skills/gushiwen", pinned(
        "ichangting/taotao-skills", "4d6f67f4d88bcabc1f4f1fd857e0d92e7fb67575",
        ["LICENSE", "skills/gushiwen/references/文言词表/江西省中考文言文高频词表.md", "skills/gushiwen/references/教材版本/统编教材版本对照表.md"],
    )),
    "字书/shuowen": ("Apache-2.0 repository", "https://github.com/shuowenjiezi/shuowen", {
        **pinned("shuowenjiezi/shuowen", "6553a350763ce4feca2c5d1cc2cad7e594dc2975", ["LICENSE", "README.md", "doc/FORMAT.md"]),
        "shuowen-data.jsonl": "https://codeload.github.com/shuowenjiezi/shuowen/zip/6553a350763ce4feca2c5d1cc2cad7e594dc2975",
    }),
    "语言标注/ud-kyoto": ("Conflicting upstream notices: UD site/README say PD; snapshot LICENSE.txt says CC-BY-SA-4.0", "https://universaldependencies.org/treebanks/lzh_kyoto/index.html", pinned(
        "UniversalDependencies/UD_Classical_Chinese-Kyoto", "b7db15b8b254f94343138966066c77203658c372",
        ["LICENSE.txt", "README.md", *(f"lzh_kyoto-ud-{part}.conllu" for part in ("train", "dev", "test"))],
    )),
    "语言标注/ud-tuecl": ("CC-BY-SA-4.0 according to publisher", "https://universaldependencies.org/treebanks/lzh_tuecl/", pinned(
        "UniversalDependencies/UD_Classical_Chinese-TueCL", "23a535f907e4930a87aed6f96ab61cbb66e6889b",
        ["LICENSE.txt", "README.md", "lzh_tuecl-ud-test.conllu"],
    )),
    "评测/gujilab-bench": ("MIT according to publisher; benchmark answers need teacher review", "https://github.com/gujilab/chinese-classical-bench", pinned(
        "gujilab/chinese-classical-bench", "4d77c55c27faef6d056cbad7693df339a2768971",
        ["LICENSE", "README.md", *(f"data/{task}.jsonl" for task in BENCH_TASKS)],
    )),
}


def inspect(path, kind):
    if kind == ".jsonl":
        with path.open(encoding="utf-8-sig") as stream:
            count = 0
            for line in stream:
                if line.strip():
                    if not isinstance(json.loads(line), dict):
                        raise ValueError("expected a JSON object")
                    count += 1
            return count, "records"
    if kind == ".json":
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(parsed, dict) and isinstance(parsed.get("articles"), list):
            return len(parsed["articles"]), "articles"
        if isinstance(parsed, dict) and parsed.get("title") == "古文觀止":
            return sum(len(volume["content"]) for volume in parsed["content"]), "articles"
        return len(parsed), "top_level_items"
    if kind == ".conllu":
        with path.open(encoding="utf-8-sig") as stream:
            return sum(line.startswith("# sent_id = ") for line in stream), "sentences"
    path.read_text(encoding="utf-8-sig")
    return None, None


def verified_record(target, url, license_note, project, kind=None):
    with target.open("rb") as stream:
        prefix = stream.read(160).lower().lstrip()
        if not prefix or prefix.startswith((b"version https://git-lfs", b"<!doctype html", b"<html", b"<?xml")):
            raise ValueError("received a pointer, HTML error or empty file")
        stream.seek(0)
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    count, unit = inspect(target, kind or target.suffix.lower())
    if count == 0:
        raise ValueError("validated data file has no records")
    return {"file": target.relative_to(ROOT).as_posix(), "url": url, "project": project, "license_note": license_note,
            "bytes": target.stat().st_size, "sha256": digest, "count": count, "unit": unit}


def repair_article_json(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    def repair_line(match):
        pieces = []
        slashes = 0
        for character in match[2]:
            if character == '"' and slashes % 2 == 0:
                pieces.append("\\")
            pieces.append(character)
            slashes = slashes + 1 if character == "\\" else 0
        return match[1] + "".join(pieces) + match[3]

    repaired = re.sub(r'^([ \t]*"[A-Za-z][A-Za-z0-9_]*"[ \t]*:[ \t]*")(.*)("[ \t]*,?[ \t]*\r?)$', repair_line, raw, flags=re.MULTILINE)
    return json.loads(repaired)


def download(group, name, url, license_note, project):
    target = ROOT / group / name
    target.parent.mkdir(parents=True, exist_ok=True)
    archive_conversion = name == "shuowen-data.jsonl"
    article_conversion = group == "教学参考/reciting-us" and name.endswith("/articles.json")
    conversion = ("Extract only data/<id>.json from pinned ZIP into UTF-8 JSONL" if archive_conversion else
                  "Repair unescaped ASCII quotations inside single-line strings and re-emit JSON" if article_conversion else None)
    if target.exists():
        return {**verified_record(target, url, license_note, project), **({"conversion": conversion} if conversion else {})}
    temp = target.with_name(target.name + ".part")
    transport = target.with_name(target.name + ".source.part") if conversion else temp
    try:
        req = Request(url, headers={"User-Agent": "Wenyan-Corpus-Local/1.0"})
        with urlopen(req, timeout=40) as response, transport.open("wb") as stream:
            size = 0
            while chunk := response.read(256 * 1024):
                size += len(chunk)
                if size > LIMIT:
                    raise ValueError("file exceeds per-file size limit")
                stream.write(chunk)
        if archive_conversion:
            with ZipFile(transport) as archive, temp.open("w", encoding="utf-8", newline="\n") as stream:
                names = sorted(item for item in archive.namelist() if "/data/" in item and item.endswith(".json"))
                if not 9000 <= len(names) <= 10000:
                    raise ValueError("unexpected number of dictionary files")
                for entry in names:
                    data = json.loads(archive.read(entry).decode("utf-8-sig"))
                    if not isinstance(data, dict):
                        raise ValueError("dictionary entry must be an object")
                    stream.write(json.dumps(data, ensure_ascii=False) + "\n")
        elif article_conversion:
            data = repair_article_json(transport.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or not isinstance(data.get("articles"), list) or not data["articles"]:
                raise ValueError("expected an articles array")
            if any(not isinstance(entry, dict) or not isinstance(entry.get("text"), str) for entry in data["articles"]):
                raise ValueError("article records require a text field")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        record = verified_record(temp, url, license_note, project, target.suffix.lower())
        temp.replace(target)
        return {**record, "file": target.relative_to(ROOT).as_posix(), **({"conversion": conversion} if conversion else {})}
    finally:
        temp.unlink(missing_ok=True)
        if conversion:
            transport.unlink(missing_ok=True)


def run(task):
    group, name, url, license_note, project = task
    try:
        record = download(*task)
        print(f"OK {record['file']} ({record['bytes']:,} B, {record['count'] or '-'} {record['unit'] or ''})", flush=True)
        return record, None
    except Exception as error:
        print(f"FAILED {group}/{name}: {error}", flush=True)
        return None, {"file": f"{group}/{name}", "url": url, "error": str(error)}


def main():
    tasks = [(group, name, url, license_note, project)
             for group, (license_note, project, files) in DATASETS.items() for name, url in files.items()]
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(run, tasks))
    files = [record for record, _ in outcomes if record]
    failures = [error for _, error in outcomes if error]
    manifest = {"files": files, "failures": failures}
    (ROOT / "下载清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(files)} files, {sum(item['bytes'] for item in files):,} bytes, {len(failures)} failures", flush=True)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
