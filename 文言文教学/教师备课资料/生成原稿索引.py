"""Extract searchable text and catalogue links from the teacher's source copies."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree
from zipfile import ZipFile


STATUS_LABELS = {
    "ok": "已提取",
    "empty": "未找到可提取的正文",
    "needs_ocr": "没有文本层，需要 OCR",
    "partial_needs_ocr": "部分页面没有文本，请检查是否需要 OCR",
    "pdf_tool_unavailable": "缺少可用的 PDF 提取工具",
    "unsupported": "格式暂不支持，请另存为 DOCX 或 PDF",
    "error": "读取失败",
}
SUPPORTED = {".docx", ".pdf", ".md", ".txt"}
# 老式 Word、WPS 和表格文件不静默丢弃，编入索引并提示转存，避免归档后查不到。
UNSUPPORTED = {".doc", ".wps", ".wpt", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf"}


def word_contents(path):
    with ZipFile(path) as package:
        document = ElementTree.fromstring(package.read("word/document.xml"))
        try:
            styles = ElementTree.fromstring(package.read("word/styles.xml"))
        except KeyError:
            styles = None

    namespace = document.tag.partition("}")[0] + "}"

    def tag(name):
        return namespace + name

    def value(node, name):
        child = node.find(tag(name)) if node is not None else None
        return child.get(tag("val"), "") if child is not None else ""

    def outline_level(properties):
        level = value(properties, "outlineLvl")
        return int(level) + 1 if level.isdecimal() and int(level) < 9 else 0

    style_data = {}
    if styles is not None:
        for style in styles.findall(tag("style")):
            if style.get(tag("type")) == "paragraph":
                style_data[style.get(tag("styleId"), "")] = (
                    value(style, "name"),
                    outline_level(style.find(tag("pPr"))),
                    value(style, "basedOn"),
                )

    def heading_level(paragraph):
        properties = paragraph.find(tag("pPr"))
        direct = outline_level(properties)
        if direct:
            return direct
        style_id = value(properties, "pStyle")
        visited = set()
        while style_id and style_id not in visited:
            visited.add(style_id)
            name, level, parent = style_data.get(style_id, ("", 0, ""))
            for label in (name, style_id):
                if label.lower() == "title" or label == "标题":
                    return -1
                match = re.fullmatch(r"(?:heading|标题)\s*([1-9])", label, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            if level:
                return level
            style_id = parent
        return 0

    def inline_text(node):
        # Word 拼音指南：只取被注音的正文，丢弃上方的拼音，避免「dú椟」混入引文。
        if node.tag == tag("ruby"):
            base = node.find(tag("rubyBase"))
            return inline_text(base) if base is not None else ""
        if node.tag == tag("t"):
            return node.text or ""
        if node.tag == tag("tab"):
            return "\t"
        if node.tag in {tag("br"), tag("cr")}:
            return "\n"
        if node.tag in skipped_inline:
            return ""
        return "".join(inline_text(child) for child in node)

    def elements(container, allowed):
        for child in container:
            if child.tag in allowed:
                yield child
            elif child.tag in wrappers:
                yield from elements(child, allowed)

    headings = []
    title = ""
    table_count = 0
    paragraph_tag, table_tag, row_tag, cell_tag = map(tag, ("p", "tbl", "tr", "tc"))
    skipped_inline = {
        tag(name) for name in ("pPr", "rPr", "del", "moveFrom", "drawing", "pict", "txbxContent")
    }
    wrappers = {
        tag(name) for name in ("sdt", "sdtContent", "customXml", "ins", "moveTo")
    }

    def blocks(container, include_headings=True):
        nonlocal title, table_count
        for block in elements(container, {paragraph_tag, table_tag}):
            if block.tag == paragraph_tag:
                content = inline_text(block).strip()
                if not content:
                    continue
                level = heading_level(block) if include_headings else 0
                if level:
                    heading = " ".join(content.split())
                    headings.append(heading)
                    if level == -1 and not title:
                        title = heading
                    yield f'{"#" * (1 if level == -1 else level)} {heading}'
                else:
                    yield content
                continue

            table_count += 1
            rows = [f"【表格 {table_count}】"]
            for row in elements(block, {row_tag}):
                cells = []
                for cell in elements(row, {cell_tag}):
                    content = " / ".join(blocks(cell, include_headings=False))
                    cells.append(content.replace("\n", " / "))
                rows.append(" | ".join(cells))
            yield "\n".join(rows)

    body = document.find(tag("body"))
    if body is None:
        raise ValueError("DOCX 缺少正文 XML")
    content = "\n\n".join(blocks(body))
    title = title or next(iter(headings), path.stem)
    return title, headings, table_count, content


def pdf_pages(path):
    errors = []
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        try:
            result = subprocess.run(
                [pdftotext, "-layout", "-enc", "UTF-8", str(path), "-"],
                capture_output=True,
                check=True,
                timeout=60,
            )
            pages = result.stdout.decode("utf-8-sig").split("\f")
            if pages[-1] == "":
                pages.pop()
            if pages:
                return pages
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as error:
            errors.append(type(error).__name__)

    try:
        import pymupdf
    except ImportError:
        pass
    else:
        try:
            with pymupdf.open(path) as document:
                return [page.get_text(sort=True) for page in document]
        except (OSError, RuntimeError, ValueError) as error:
            errors.append(type(error).__name__)

    try:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
    except ImportError:
        pass
    else:
        try:
            with path.open("rb") as stream:
                return [
                    page.extract_text(extraction_mode="layout") or ""
                    for page in PdfReader(stream).pages
                ]
        except (OSError, PyPdfError, ValueError) as error:
            errors.append(type(error).__name__)

    if errors:
        raise ValueError(f'可用的 PDF 工具读取失败（{"、".join(errors)}）')
    return None


def plain_text(path):
    raw = path.read_bytes()
    if b"\x00" in raw[:4096] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise ValueError("原稿含二进制字符")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16").strip()
    try:
        return raw.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        return raw.decode("gb18030").strip()


def write_text_atomic(path, text):
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        staged = Path(stream.name)
        try:
            stream.write(text)
        except Exception:
            stream.close()
            staged.unlink(missing_ok=True)
            raise
    try:
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def unsupported_record(relative_path):
    """格式不支持时也留一条记录，让老师知道归档里有这份、但查不到文字。"""
    return {
        "path": relative_path.as_posix(),
        "extract": None,
        "title": relative_path.stem,
        "kind": relative_path.suffix.lower().removeprefix("."),
        "headings": [],
        "table_count": 0,
        "page_count": None,
        "status": "unsupported",
    }


def index_document(root, path, relative_path, extract_path, previous):
    record = {
        "path": relative_path.as_posix(),
        "extract": extract_path.as_posix(),
        "title": path.stem,
        "kind": path.suffix.lower().removeprefix("."),
        "headings": [],
        "table_count": 0,
        "page_count": None,
        "status": "ok",
    }
    extract = root / extract_path
    content = ""
    try:
        if record["kind"] == "docx":
            title, headings, table_count, content = word_contents(path)
            record.update(title=title, headings=headings, table_count=table_count)
            if not content:
                record["status"] = "empty"
        elif record["kind"] == "pdf":
            with path.open("rb") as stream:
                record["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            if (
                previous.get("sha256") == record["sha256"]
                and previous.get("status") == "ok"
                and previous.get("extract") == record["extract"]
                and extract.is_file()
            ):
                return previous
            pages = pdf_pages(path)
            if pages is None:
                record["status"] = "pdf_tool_unavailable"
            else:
                record["page_count"] = len(pages)
                readable = [page.strip() for page in pages]
                if not any(readable):
                    record["status"] = "needs_ocr" if pages else "empty"
                elif not all(readable):
                    record["status"] = "partial_needs_ocr"
                content = "\n\n".join(
                    f"【第 {number} 页】\n{page or '（本页未提取到文字）'}"
                    for number, page in enumerate(readable, 1)
                )
        else:
            content = plain_text(path)
            record["headings"] = re.findall(r"^\s*#{1,9}\s+(.+)$", content, re.M)
            if not content:
                record["status"] = "empty"
    except Exception as error:
        record["status"] = "error"
        content = f"读取异常（{type(error).__name__}）"

    extract.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(
        extract,
        f'原稿：{record["path"]}\n状态：{STATUS_LABELS[record["status"]]}\n\n{content}\n',
    )
    return record


def catalogue(records):
    status_counts = Counter(record["status"] for record in records)
    file_counts = Counter(record["kind"].upper() for record in records)
    lines = ["# 教师备课原稿目录", "", f"共 {len(records)} 份原稿。"]
    if file_counts:
        lines.append("文件类型：" + "，".join(f"{kind} {count} 份" for kind, count in file_counts.items()) + "。")
        lines.append("提取状态：" + "，".join(
            f"{STATUS_LABELS[status]} {count} 份" for status, count in status_counts.items()
        ) + "。")

    groups = {}
    for record in records:
        parts = record["path"].split("/")
        first_folder = parts[1] if len(parts) > 2 else ""
        groups.setdefault(first_folder, []).append(record)

    for folder, entries in groups.items():
        lines.extend(["", f"## {folder or '根目录'}（{len(entries)} 份）", ""])
        for record in entries:
            source = quote("../" + record["path"], safe="/")
            label = record["path"].split("/")[-1]
            label = label.replace("\\", r"\\").replace("[", r"\[").replace("]", r"\]")
            if record["extract"]:
                extract = quote(record["extract"].removeprefix("索引/"), safe="/")
                lines.append(f'- [{label}]({source}) · [文字摘录]({extract}) · {STATUS_LABELS[record["status"]]}')
            else:
                lines.append(f'- [{label}]({source}) · {STATUS_LABELS[record["status"]]}（未提取文字）')

    skipped = [record for record in records if record["status"] == "unsupported"]
    if skipped:
        lines.extend(["", "## 未纳入检索的格式", "",
                      "下列文件已归档，但当前只提取 DOCX、PDF、MD、TXT。转存为 DOCX 或 PDF 后重跑本脚本即可检索。", ""])
        lines.extend(f'- {record["path"]}（{record["kind"].upper()}）' for record in skipped)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="提取原始资料，并重建教师备课原稿索引。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    root = parser.parse_args().root.resolve()
    originals = root / "原始资料"
    if not originals.is_dir():
        parser.exit(1, f"找不到原始资料目录：{originals}\n")

    records = []
    index_dir = root / "索引"
    index_path = index_dir / "原稿索引.json"
    try:
        previous = {
            item["path"]: item
            for item in json.loads(index_path.read_text(encoding="utf-8"))["records"]
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
    except (OSError, ValueError, TypeError, KeyError):
        previous = {}
    paths = sorted(originals.rglob("*"), key=lambda path: path.as_posix().casefold())
    for path in paths:
        if path.name.startswith("~$"):
            continue
        if not path.is_file() or not path.resolve().is_relative_to(originals.resolve()):
            continue
        relative_path = path.relative_to(root)
        suffix = path.suffix.lower()
        if suffix in UNSUPPORTED:
            records.append(unsupported_record(relative_path))
            continue
        if suffix not in SUPPORTED:
            continue
        extract = Path("索引", "摘录", path.relative_to(originals)).with_name(path.name + ".txt")
        records.append(index_document(root, path, relative_path, extract, previous.get(relative_path.as_posix(), {})))

    index_dir.mkdir(exist_ok=True)
    write_text_atomic(index_dir / "原稿目录.md", catalogue(records))
    write_text_atomic(
        index_path, json.dumps({"records": records}, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"已编目 {len(records)} 份原稿。")


if __name__ == "__main__":
    sys.exit(main())
