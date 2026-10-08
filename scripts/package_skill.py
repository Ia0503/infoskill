#!/usr/bin/env python3
"""Export only runtime files into an infoskill/ ZIP, without overwriting."""

import argparse
from pathlib import Path
import zipfile

from _common import is_link, is_private

ROOT_FILES = ("SKILL.md", "README.md")
RESOURCE_DIRS = ("agents", "references", "assets", "scripts")


def runtime_files(root):
    root = Path(root).resolve()
    files = []
    for name in ROOT_FILES:
        path = root / name
        if not path.is_file() or is_link(path):
            raise ValueError(f"Required runtime file missing or linked: {name}")
        files.append(path)
    license_file = root / "LICENSE"
    if license_file.is_file():
        if is_link(license_file):
            raise ValueError("Linked LICENSE file cannot be packaged.")
        files.append(license_file)
    for name in RESOURCE_DIRS:
        folder = root / name
        if is_link(folder):
            raise ValueError(f"Linked resource directory: {name}")
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            relative = path.relative_to(root)
            if is_link(path) or not path.resolve().is_relative_to(root):
                raise ValueError(f"Linked or escaping resource: {relative}")
            if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_file():
                if is_private(path):
                    raise ValueError(f"Private configuration cannot be packaged: {relative}")
                files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def package(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Output already exists; choose a new path.")
    if output.is_relative_to(root / "info") or output.is_relative_to(root / "test"):
        raise ValueError("Choose an export directory outside info/ and test/.")
    files = runtime_files(root)
    if output in files or any(output.is_relative_to(root / d) for d in RESOURCE_DIRS):
        raise ValueError("Output cannot be inside runtime resource directories.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, "infoskill/" + file.relative_to(root).as_posix())
    return output, len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/infoskill.zip"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        output, count = package(args.root, args.output)
        print(f"Exported {count} files: {output}")
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
