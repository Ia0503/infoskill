"""Shared file names and bounded, private-by-default inventory helpers."""

from pathlib import Path
import os
import re

DOCUMENTS = (
    "01-项目总览与架构.md", "02-目录结构与文件详解.md",
    "03-技术选型与对比分析.md", "04-核心模块深度剖析.md",
    "05-测试评测与部署维护.md", "06-面试高频问题与回答要点.md",
    "07-开发日志与阶段总结.md",
)
EXCLUDED = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "dist", "build", "coverage", "runtime",
    ".next", ".nuxt", ".cache", ".codex", ".agents", ".aws",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".pfx", ".p12"}
LOG_SUFFIXES = {".md", ".txt", ".log", ".jsonl"}


def is_link(path):
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def is_private(path):
    name = path.name.lower()
    return (
        name == ".env" or name.startswith(".env.") and name != ".env.example"
        or path.suffix.lower() in SENSITIVE_SUFFIXES
        or name in {"credentials", "id_rsa", "id_ed25519", ".npmrc", ".pypirc"}
    )


def inventory(root, limit=1500):
    """Walk in a stable order without following links or outputting file contents."""
    root = Path(root)
    found = []
    truncated = False
    for folder, dirs, files in os.walk(root, followlinks=False):
        here = Path(folder)
        relative = here.relative_to(root)
        dirs[:] = sorted(
            d for d in dirs if d.lower() not in EXCLUDED
            and not (relative.as_posix() == "test" and d == "results")
            and not is_link(here / d)
        )
        for name in sorted(files):
            path = here / name
            if is_link(path) or is_private(path):
                continue
            if len(found) >= limit:
                truncated = True
                return found, truncated
            found.append(path.relative_to(root).as_posix())
    return found, truncated


def log_status(root):
    folder = Path(root) / "info" / "log"
    if not folder.is_dir() or is_link(folder) or not folder.resolve().is_relative_to(Path(root).resolve()):
        return {"state": "missing", "records": [], "unknown_formats": []}
    records, unknown = [], []
    files, truncated = inventory(folder, 300)
    for relative in files:
        path = folder / relative
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in LOG_SUFFIXES:
            unknown.append(relative)
            continue
        try:
            # Read only a bounded prefix; semantic eligibility is still the agent's job.
            with path.open("rb") as stream:
                sample = stream.read(8192).decode("utf-8-sig")
        except (OSError, UnicodeError):
            unknown.append(relative)
            continue
        prose = re.sub(r"<!--.*?-->", "", sample, flags=re.S).strip()
        placeholder = prose.lower().strip("# \r\n") in {
            "todo", "待填写", "待补充", "开发日志", "project log", "placeholder",
        }
        if len(prose) >= 20 and not placeholder:
            records.append(relative)
    return {
        "state": "readable_records" if records else "no_readable_records",
        "records": records, "unknown_formats": unknown, "truncated": truncated,
        "note": "Heuristic only; confirm these are actual development records.",
    }
