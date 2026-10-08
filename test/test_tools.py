"""Observable checks use isolated synthetic projects; no live services."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _common import DOCUMENTS, inventory, log_status
from inspect_project import inspect
from package_skill import package, runtime_files
from validate_info import validate

RESULTS = ROOT / "test" / "results"


class ToolTests(unittest.TestCase):
    def setUp(self):
        RESULTS.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="case-", dir=RESULTS)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "中文 项目"
        self.root.mkdir()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def docs(self, count=6):
        for name in DOCUMENTS[:count]:
            self.write("info/" + name, "# Synthetic document\n\nActual checked content.\n")

    def test_scan_excludes_private_values_and_heavy_directories(self):
        self.write(".env", "DO_NOT_EXPORT_THIS_VALUE")
        self.write("private.key", "DO_NOT_EXPORT_THIS_VALUE")
        self.write(".env.example", "API_KEY=YOUR_API_KEY_HERE")
        self.write("node_modules/a.js", "irrelevant")
        self.write("runtime/uploads/data.txt", "private")
        self.write("test/results/old.log", "private")
        self.write("src/main.py", "print('sample')")
        self.write("package.json", json.dumps({"scripts": {"dev": "DO_NOT_EXPORT_THIS_VALUE"}}))
        report = inspect(self.root)
        encoded = json.dumps(report)
        self.assertNotIn("DO_NOT_EXPORT_THIS_VALUE", encoded)
        self.assertNotIn(".env", report["files"])
        self.assertIn(".env.example", report["files"])
        self.assertEqual(report["node_manifests"][0]["script_names"], ["dev"])
        self.assertFalse(any(f.startswith(("runtime/", "node_modules/", "test/results/")) for f in report["files"]))

    def test_scan_cap_and_order_are_observable(self):
        for i in range(4):
            self.write(f"src/{i}.py", "pass")
        files, truncated = inventory(self.root, limit=2)
        self.assertEqual(files, ["src/0.py", "src/1.py"])
        self.assertTrue(truncated)

    def test_invalid_manifest_does_not_stop_inventory(self):
        self.write("package.json", "not json")
        self.write("src/main.js", "sample")
        report = inspect(self.root)
        self.assertIn("note", report["node_manifests"][0])
        self.assertIn("src/main.js", report["files"])

    def test_synthetic_project_configs_are_discovered(self):
        for name, expected in (("node-project", "package.json"), ("python-project", "pyproject.toml"), ("compose-project", "compose.yaml")):
            report = inspect(ROOT / "test" / "fixtures" / name)
            entries = report["configs"] if expected != "package.json" else [m["path"] for m in report["node_manifests"]]
            self.assertIn(expected, entries)

    def test_no_logs_requires_only_six_documents(self):
        self.docs()
        report = validate(self.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(report["checked"]), 6)

    def test_placeholder_directory_is_not_development_history(self):
        self.docs()
        self.write("info/log/.gitkeep", "")
        self.write("info/log/project_log.md", "<!-- a long placeholder only, not a real record -->")
        self.assertFalse(log_status(self.root)["records"])
        self.assertTrue(validate(self.root)["ok"])

    def test_readable_logs_require_document_seven(self):
        self.docs()
        self.write("info/log/project_log.md", "# Record\n2026-01-01: changed the synthetic entry and verified its output.\n")
        self.assertFalse(validate(self.root)["ok"])
        self.docs(7)
        self.assertTrue(validate(self.root)["ok"])

    def test_unknown_log_format_is_reported_for_manual_review(self):
        self.docs()
        self.write("info/log/notes.rst", "A genuine-looking custom-format log is not classified automatically.")
        self.assertTrue(validate(self.root)["warnings"])

    def test_existing_seven_without_logs_is_preserved(self):
        self.docs(7)
        file = self.root / "info" / DOCUMENTS[6]
        before = file.read_bytes()
        report = validate(self.root)
        self.assertTrue(report["ok"])
        self.assertTrue(report["warnings"])
        self.assertEqual(file.read_bytes(), before)

    def test_partial_validation_does_not_require_other_documents(self):
        self.write("info/" + DOCUMENTS[3], "# Actual module\n\nNo other document was requested.\n")
        self.assertTrue(validate(self.root, ["04"])["ok"])
        self.assertFalse(validate(self.root)["ok"])

    def test_links_resolve_under_chinese_and_space_paths(self):
        self.docs()
        self.write("src/模块 文件.py", "pass")
        self.write("info/" + DOCUMENTS[0], "# Link\n\n[source](<../src/模块 文件.py>)\n")
        self.assertTrue(validate(self.root)["ok"])
        self.write("info/" + DOCUMENTS[0], "# Link\n\n[source](../src/missing.py)\n")
        self.assertFalse(validate(self.root)["ok"])

    def test_absolute_and_escaping_links_are_rejected(self):
        self.docs()
        self.write("info/" + DOCUMENTS[0], "# Links\n\n[file](C:/private/source.py)\n[out](../../outside.md)\n")
        report = validate(self.root)
        self.assertTrue(any("Absolute" in e for e in report["errors"]))
        self.assertTrue(any("leaves project" in e for e in report["errors"]))

    def test_code_fence_examples_do_not_become_links(self):
        self.docs()
        self.write("info/" + DOCUMENTS[0], "# Code\n\n````text\n[x](missing.py)\n```\n````\n")
        self.assertTrue(validate(self.root)["ok"])
        self.write("info/" + DOCUMENTS[0], "# Code\n\n```python\npass\n")
        self.assertFalse(validate(self.root)["ok"])

    def test_launchers_require_adjacent_txt_and_consistent_names(self):
        self.docs()
        self.write("info/启动.bat", "@echo off\nexit /b 0\n")
        self.assertFalse(validate(self.root)["ok"])
        self.write("info/脚本使用说明.txt", "双击启动.bat，运行样例；此文件不启动真实服务。")
        self.assertTrue(validate(self.root)["ok"])
        self.write("info/关闭.ps1", "exit 0\n")
        self.assertFalse(validate(self.root)["ok"])

    def test_unfinished_templates_and_bat_bom_are_rejected(self):
        self.docs()
        self.write("info/" + DOCUMENTS[0], "<!-- infoskill:template -->\n# Draft\n")
        self.assertFalse(validate(self.root)["ok"])
        self.docs()
        self.write("info/启动.bat", "\ufeff@echo off\nexit /b 0\n")
        self.write("info/脚本使用说明.txt", "启动.bat 的说明。")
        self.assertTrue(any("BOM" in e for e in validate(self.root)["errors"]))

    def test_validation_is_read_only_and_repeatable(self):
        self.docs()
        personal = self.write("info/personal.txt", "Preserve this personal note.")
        snapshot = {p: p.read_bytes() for p in (self.root / "info").rglob("*") if p.is_file()}
        validate(self.root)
        validate(self.root)
        self.assertEqual(snapshot, {p: p.read_bytes() for p in snapshot})
        self.assertTrue(personal.exists())

    def test_export_is_allowlisted_and_no_overwrite(self):
        self.write("SKILL.md", "---\nname: infoskill\ndescription: Sample\n---\n")
        self.write("README.md", "# Sample")
        self.write("references/rules.md", "Sample rules")
        self.write("info/log/private.md", "Do not package")
        self.write("test/results/private.txt", "Do not package")
        self.write("scripts/__pycache__/cache.pyc", "Do not package")
        output = self.root / "dist" / "skill.zip"
        package(self.root, output)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {"infoskill/SKILL.md", "infoskill/README.md", "infoskill/references/rules.md"})
        before = output.read_bytes()
        with self.assertRaises(ValueError):
            package(self.root, output)
        self.assertEqual(output.read_bytes(), before)

    def test_private_runtime_configuration_blocks_packaging(self):
        self.write("SKILL.md", "skill")
        self.write("README.md", "readme")
        self.write("scripts/.env", "DO_NOT_EXPORT_THIS_VALUE")
        with self.assertRaises(ValueError):
            runtime_files(self.root)

    def test_export_cannot_include_its_own_output(self):
        self.write("SKILL.md", "skill")
        self.write("README.md", "readme")
        with self.assertRaises(ValueError):
            package(self.root, self.root / "scripts" / "output.zip")

    @unittest.skipUnless(os.name == "nt", "Windows directory junction")
    def test_junctions_are_not_followed_by_scan_or_validation(self):
        target = Path(self.temporary.name) / "outside"
        target.mkdir()
        (target / "private.txt").write_text("DO_NOT_EXPORT_THIS_VALUE", encoding="utf-8")
        junction = self.root / "info"
        run = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(any("private.txt" in p for p in inventory(self.root)[0]))
        self.assertFalse(validate(self.root)["ok"])
        self.assertFalse(log_status(self.root)["records"])

    @unittest.skipUnless(os.name == "nt", "Windows BAT/PowerShell bridge")
    def test_bat_powershell_bridge_propagates_child_exit(self):
        executable = os.environ.get("INFOSKILL_PWSH") or shutil.which("pwsh")
        if not executable:
            self.skipTest("PowerShell unavailable")
        template = (ROOT / "assets" / "launchers" / "run-powershell.bat.template").read_text(encoding="utf-8")
        script = template.replace("{{POWERSHELL}}", Path(executable).name).replace("{{SCRIPT_NAME}}", "helper.ps1")
        bat = self.write("info/启动.bat", script)
        self.write("info/helper.ps1", "exit 7\n")
        env = dict(os.environ, INFOSKILL_NO_PAUSE="1", PATH=str(Path(executable).parent) + os.pathsep + os.environ.get("PATH", ""))
        run = subprocess.run(["cmd.exe", "/d", "/c", "call", str(bat)], cwd=ROOT, env=env, capture_output=True, timeout=20)
        self.assertEqual(run.returncode, 7, run.stdout + run.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows BAT execution")
    def test_bat_locates_project_and_preserves_failure_exit(self):
        template = (ROOT / "assets" / "launchers" / "run-command.bat.template").read_text(encoding="utf-8")
        launcher = template.replace("rem infoskill:template - replace tool and command for the actual project.\n", "").replace("{{TOOL}}", "infoskill-test-tool").replace("{{COMMAND}}", "infoskill-test-tool.cmd run")
        bat = self.write("info/启动.bat", launcher)
        tools = self.root / "fake tools"
        tools.mkdir()
        command = tools / "infoskill-test-tool.cmd"
        command.write_text('@echo off\nif not "%CD%"=="%INFOSKILL_EXPECTED_ROOT%" exit /b 23\nif not "%~1"=="run" exit /b 24\n> "%INFOSKILL_RECORD%" echo invoked\nexit /b %INFOSKILL_TEST_EXIT%\n', encoding="ascii")
        record = self.root / "invocation.txt"
        env = dict(os.environ, INFOSKILL_NO_PAUSE="1", INFOSKILL_EXPECTED_ROOT=str(self.root), INFOSKILL_RECORD=str(record), PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""))
        for exit_code in (0, 7):
            env["INFOSKILL_TEST_EXIT"] = str(exit_code)
            run = subprocess.run(["cmd.exe", "/d", "/c", "call", str(bat)], cwd=ROOT, env=env, capture_output=True, timeout=15)
            self.assertEqual(run.returncode, exit_code, run.stdout + run.stderr)
            self.assertEqual(record.read_text().strip(), "invoked")

    @unittest.skipUnless(os.name == "nt", "Windows BAT execution")
    def test_bat_missing_tool_fails_without_running_command(self):
        template = (ROOT / "assets" / "launchers" / "run-command.bat.template").read_text(encoding="utf-8")
        launcher = template.replace("{{TOOL}}", "__infoskill_absent_tool__").replace("{{COMMAND}}", "echo unexpected")
        bat = self.write("info/run.bat", launcher)
        run = subprocess.run(["cmd.exe", "/d", "/c", "call", str(bat)], env=dict(os.environ, INFOSKILL_NO_PAUSE="1"), capture_output=True, timeout=15)
        self.assertEqual(run.returncode, 1)
        self.assertNotIn(b"unexpected", run.stdout)

    def test_powershell_helper_uses_real_exit_status(self):
        executable = os.environ.get("INFOSKILL_PWSH") or shutil.which("pwsh")
        if not executable:
            self.skipTest("PowerShell unavailable")
        template = (ROOT / "assets" / "launchers" / "run-command.ps1.template").read_text(encoding="utf-8")
        # Use the same interpreter as a harmless child, instead of a project service.
        helper = template.replace("{{TOOL}}", Path(executable).name).replace("{{ARGUMENTS}}", '-NoProfile -Command "exit 7"')
        path = self.write("info/helper.ps1", helper)
        env = dict(os.environ, PATH=str(Path(executable).parent) + os.pathsep + os.environ.get("PATH", ""))
        run = subprocess.run([executable, "-NoProfile", "-File", str(path)], cwd=ROOT, env=env, capture_output=True, timeout=20)
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn(b"exit code 7", run.stderr)


if __name__ == "__main__":
    unittest.main()
