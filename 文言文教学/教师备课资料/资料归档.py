"""将教师明确提供的文件原样归档到本脚本旁的「原始资料」。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


ARCHIVE = Path(__file__).resolve().parent / "原始资料"
CHUNK_SIZE = 1024 * 1024


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def is_link(path):
    return path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    )


def reject_link(path):
    if is_link(path):
        raise ValueError(f"跳过链接或目录联接：{path}")


def tree_files(root):
    def walk_error(error):
        raise error

    for directory, folders, names in os.walk(root, onerror=walk_error):
        base = Path(directory)
        folders[:] = sorted(name for name in folders if not is_link(base / name))
        for name in sorted(names):
            source = base / name
            if not is_link(source) and source.is_file():
                yield source


def source_files(files, source_root, archive):
    if source_root is None:
        for filename in files:
            yield Path(filename).expanduser().absolute(), None
        return

    root = Path(source_root).expanduser().absolute()
    reject_link(root)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"目录不存在：{root}")
    destination = archive.resolve()
    if root.is_relative_to(destination) or destination.is_relative_to(root):
        raise ValueError("导入目录和原始资料目录不能互相包含。")
    for source in tree_files(root):
        yield source, source.relative_to(root)


def stage_file(source, staged):
    reject_link(source)
    if not source.is_file():
        raise ValueError(f"文件不存在或不是普通文件：{source}")
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as original, staged.open("wb") as copy:
        before = os.fstat(original.fileno())
        while block := original.read(CHUNK_SIZE):
            copy.write(block)
            digest.update(block)
            size += len(block)
        after = os.fstat(original.fileno())
        if (
            size != before.st_size
            or size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise ValueError("复制期间原始文件发生变化，请重试。")
        copy.flush()
        os.fsync(copy.fileno())
    sha256 = digest.hexdigest()
    if file_digest(staged) != sha256:
        raise ValueError("复制文件的 SHA-256 校验失败。")
    return sha256, size


def checked_destination(archive, relative):
    directory = archive
    for name in relative.parts[:-1]:
        directory = directory / name
        if is_link(directory):
            raise ValueError(f"归档目标经过链接或目录联接：{directory}")
        directory.mkdir(exist_ok=True)
    return archive / relative


def publish(staged, destination, sha256):
    reject_link(destination)
    try:
        # POSIX rename may replace a destination. A hard link publishes
        # the completed file only if the destination does not already exist.
        if os.name == "nt":
            staged.rename(destination)
        else:
            os.link(staged, destination)
        return "imported"
    except OSError:
        reject_link(destination)
        if not destination.exists():
            raise
        if destination.is_file() and file_digest(destination) == sha256:
            return "unchanged"
        return "conflict"


def import_files(files, source_root, archive=ARCHIVE, folder=None):
    results = []
    reject_link(archive)
    archive.mkdir(exist_ok=True)
    # A staging directory beside the archive shares its volume and keeps
    # incomplete copies out of the browseable archive.
    with tempfile.TemporaryDirectory(prefix=".资料归档-", dir=archive.parent) as temporary:
        staged = Path(temporary) / "copy"
        try:
            for source, relative in source_files(files, source_root, archive):
                result = {
                    "filename": source.name,
                    "source": str(source),
                    "sha256": None,
                    "path": None,
                    "relative_path": None,
                }
                results.append(result)
                try:
                    sha256, size = stage_file(source, staged)
                    if relative is None:
                        relative = Path(folder or sha256) / source.name
                    result.update(
                        sha256=sha256,
                        size=size,
                        path=str(archive / relative),
                        relative_path=relative.as_posix(),
                    )
                    destination = checked_destination(archive, relative)
                    result["status"] = publish(staged, destination, sha256)
                    if result["status"] == "conflict":
                        result["error"] = "归档路径已有不同内容，原归档已保留。"
                except (OSError, ValueError) as error:
                    result.update(status="error", error=str(error))
                finally:
                    staged.unlink(missing_ok=True)
        except (OSError, ValueError) as error:
            results.append({"status": "error", "error": str(error)})
    return results


def list_files(archive=ARCHIVE):
    reject_link(archive)
    if not archive.exists():
        return []
    return [
        {
            "filename": source.name,
            "sha256": file_digest(source),
            "size": source.stat().st_size,
            "path": str(source),
            "relative_path": source.relative_to(archive).as_posix(),
            "status": "archived",
        }
        for source in tree_files(archive)
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import", help="归档明确指定的文件或目录")
    ingest.add_argument("files", nargs="*", help="明确提供的文件路径")
    ingest.add_argument("--root", help="保持相对路径的资料目录")
    ingest.add_argument("--folder", help="归档单独文件时指定分类名称，例如 初中部门")
    ingest.add_argument("--json", action="store_true", help="输出 JSON")
    listing = commands.add_parser("list", help="列出归档中的文件和校验值")
    listing.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()
    if args.command == "import" and bool(args.root) == bool(args.files):
        ingest.error("请提供文件路径或 --root DIRECTORY，两种方式只能选一种。")
    if args.command == "import" and args.folder is not None:
        name = args.folder.strip()
        if args.root or not name or name in {".", ".."} or name.endswith(".") or any(
            char in '<>:"/\\|?*' or ord(char) < 32 for char in name
        ):
            ingest.error("--folder 只用于单独归档文件，请给一个分类目录名。")
        args.folder = name

    try:
        if args.command == "import":
            files = import_files(args.files, args.root, folder=args.folder)
        else:
            files = list_files()
    except (OSError, ValueError) as error:
        files = [{"status": "error", "error": str(error)}]
    counts = {
        key: sum(file["status"] == value for file in files)
        for key, value in (
            ("imported", "imported"), ("unchanged", "unchanged"),
            ("conflicts", "conflict"), ("errors", "error"), ("archived", "archived"),
        )
    }
    failed = counts["conflicts"] or counts["errors"]
    if args.json:
        print(json.dumps({"status": "error" if failed else "ok", **counts, "files": files},
                         ensure_ascii=False, indent=2))
    else:
        labels = {
            "imported": "已归档", "unchanged": "已存在", "conflict": "内容冲突",
            "error": "归档错误", "archived": "已归档",
        }
        for file in files:
            details = [file.get("path") or file.get("filename"), file.get("sha256"),
                       file.get("error")]
            print(f"{labels[file['status']]}  " + "  ".join(part for part in details if part))
        if not files:
            print("没有归档文件。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
