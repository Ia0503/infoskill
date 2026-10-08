#!/usr/bin/env python3
"""Check generated files and inline links; source/semantic review is separate."""

import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from _common import DOCUMENTS, is_link, log_status


def markdown_body(text):
    """Skip code blocks while checking prose; recognize fenced code lengths."""
    prose = []
    marker, length = None, 0
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if match:
            token, tail = match.groups()
            if marker is None:
                marker, length = token[0], len(token)
            elif token[0] == marker and len(token) >= length and not tail.strip():
                marker = None
            continue
        if marker is None:
            prose.append(line)
    return "\n".join(prose), marker is None


def validate(root, only=None):
    root = Path(root).resolve()
    info = root / "info"
    errors, warnings, checked = [], [], []
    if is_link(info) or not info.resolve().is_relative_to(root):
        return {"ok": False, "checked": [], "logs": {}, "errors": ["info/ cannot be a linked or escaping directory."], "warnings": []}
    logs = log_status(root)
    has_logs = bool(logs["records"])
    expected = DOCUMENTS[:7 if has_logs else 6]
    if only:
        expected = tuple(DOCUMENTS[int(n) - 1] for n in dict.fromkeys(only))
    if logs.get("unknown_formats") or logs.get("truncated"):
        warnings.append("Some log files need manual eligibility review.")
    if not has_logs and (info / DOCUMENTS[6]).exists():
        warnings.append("Document 07 exists without recognized logs; preserve it and review its status.")
    for name in expected:
        file = info / name
        if not file.is_file() or is_link(file):
            errors.append(f"Missing or linked document: {name}")
            continue
        try:
            text = file.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            errors.append(f"Document is not readable UTF-8: {name}")
            continue
        checked.append(name)
        if not text.strip():
            errors.append(f"Empty document: {name}")
        if "infoskill:template" in text or re.search(r"\{\{[^\n}]+\}\}|\[待填写\]", text):
            errors.append(f"Unfinished template: {name}")
        prose, closed = markdown_body(text)
        if not closed:
            errors.append(f"Unclosed code fence: {name}")
        for match in re.finditer(r"!?\[[^\]\n]*\]\((<[^>\n]+>|[^)\n]+)\)", prose):
            target = match.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            else:
                target = re.sub(r"\s+[\"'][^\n]*[\"']$", "", target)
            parts = urlsplit(target)
            # Treat Windows drive paths before general URI handling.
            if re.match(r"^[A-Za-z]:[/\\]", target) or target.startswith(("/", "\\")) or parts.scheme == "file":
                errors.append(f"Absolute local link in {name}: {target}")
                continue
            if parts.scheme or parts.netloc or not parts.path:
                continue
            destination = (file.parent / unquote(parts.path)).resolve()
            if not destination.is_relative_to(root):
                errors.append(f"Local link leaves project in {name}: {target}")
            elif not destination.exists():
                errors.append(f"Broken local link in {name}: {target}")
            if not has_logs and parts.path.endswith(DOCUMENTS[6]) and not destination.exists():
                errors.append(f"Document 07 navigation must be omitted in {name}.")
    launchers = []
    if info.is_dir():
        launchers = [
            p for p in info.iterdir()
            if p.is_file() and p.suffix.lower() in {".bat", ".cmd", ".ps1", ".vbs", ".sh"}
        ]
    if launchers:
        guide = info / "脚本使用说明.txt"
        if not guide.is_file() or is_link(guide):
            errors.append("Launchers require adjacent 脚本使用说明.txt.")
        else:
            try:
                text = guide.read_text(encoding="utf-8-sig")
                if not text.strip() or "infoskill:template" in text:
                    errors.append("Launcher TXT is empty or unfinished.")
                for launcher in launchers:
                    if launcher.name not in text:
                        errors.append(f"Launcher TXT does not mention {launcher.name}.")
            except (OSError, UnicodeError):
                errors.append("Launcher TXT must be readable UTF-8.")
        for launcher in launchers:
            if is_link(launcher):
                errors.append(f"Linked launcher cannot be checked: {launcher.name}")
                continue
            try:
                raw = launcher.read_bytes()
                if launcher.suffix.lower() in {".bat", ".cmd"} and raw.startswith(b"\xef\xbb\xbf"):
                    errors.append(f"BAT/CMD must not have UTF-8 BOM: {launcher.name}")
                if b"infoskill:template" in raw or re.search(rb"\{\{[^\r\n}]+\}\}", raw):
                    errors.append(f"Unfinished launcher template: {launcher.name}")
            except OSError:
                errors.append(f"Cannot read launcher: {launcher.name}")
    return {"ok": not errors, "checked": checked, "logs": logs, "errors": errors, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--only", action="append", choices=[f"{n:02}" for n in range(1, 8)])
    args = parser.parse_args()
    if not args.project.is_dir():
        parser.error("Project directory does not exist")
    report = validate(args.project, args.only)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
