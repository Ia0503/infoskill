#!/usr/bin/env python3
"""Print a bounded project inventory, never configuration values or log text."""

import argparse
import json
from pathlib import Path
import subprocess

from _common import inventory, log_status


def inspect(root, limit=1500):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Project directory does not exist.")
    files, truncated = inventory(root, limit)
    packages = []
    for relative in files:
        path = root / relative
        if path.name != "package.json":
            continue
        item = {"path": relative}
        try:
            if path.stat().st_size > 256_000:
                item["note"] = "Manifest too large; inspect selectively."
            else:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(data, dict):
                    raise ValueError("Manifest is not an object.")
                scripts = data.get("scripts", {})
                # Commands may contain credentials: expose names, never their values.
                item["script_names"] = sorted(scripts) if isinstance(scripts, dict) else []
                item["lockfiles"] = [
                    name for name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock")
                    if (path.parent / name).is_file()
                ]
        except (OSError, UnicodeError, ValueError):
            item["note"] = "Manifest unreadable or invalid; inspect manually."
        packages.append(item)
    config_names = {
        "pyproject.toml", "requirements.txt", "compose.yaml", "compose.yml",
        "docker-compose.yml", "docker-compose.yaml", "Dockerfile", ".env.example",
        "AGENTS.md", "CLAUDE.md", "Makefile", "Cargo.toml", "go.mod",
    }
    git = {"available": False}
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if top.returncode == 0:
            head = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            status = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            git = {
                "available": True,
                "root_matches_target": Path(top.stdout.strip()).resolve() == root,
                "head": head.stdout.strip() if head.returncode == 0 else None,
                "dirty": bool(status.stdout) if status.returncode == 0 else None,
            }
    except (OSError, subprocess.TimeoutExpired):
        git["note"] = "Git unavailable or timed out."
    return {
        "files": files, "truncated": truncated, "limit": limit,
        "configs": [f for f in files if Path(f).name in config_names],
        "node_manifests": packages, "logs": log_status(root), "git": git,
        "note": "Inventory only. Read relevant source to determine behavior and launcher format.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000:
        parser.error("--limit must be between 1 and 10000")
    try:
        print(json.dumps(inspect(args.project, args.limit), ensure_ascii=False, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
