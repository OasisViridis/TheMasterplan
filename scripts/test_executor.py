#!/usr/bin/env python3
"""Unit and temp-repo integration tests for the /TheMasterplan executor (PR A).

Loads ``skills/themasterplan/scripts/tmlib`` via importlib and drives
the real executor against temporary directories; the TheMasterplan repository's own
``distribution/`` package is used as the fixture source.

用法: python -m unittest scripts.test_executor -v
"""

from __future__ import annotations

import importlib.util
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXECUTOR_DIR = REPO_ROOT / "skills" / "themasterplan" / "scripts"

sys.path.insert(0, str(EXECUTOR_DIR))
from tmlib import TheMasterplanError, PathSafetyError  # noqa: E402
from tmlib.apply import EXECUTOR_FILES, apply_adopt  # noqa: E402
from tmlib.inspect import detect_status, inspect  # noqa: E402
from tmlib.manifest import ManifestError, load_manifest  # noqa: E402
from tmlib.planning import adopt_plan_digest, plan_adopt  # noqa: E402
from tmlib.source import read_package_file, resolve_local  # noqa: E402
from tmlib.util import safe_join, sha256_of_file, write_json_atomic  # noqa: E402
from tmlib.verify import verify  # noqa: E402
from themasterplan import build_parser  # noqa: E402

PACKAGE_ROOT = REPO_ROOT  # TheMasterplan repo root contains distribution/
TEST_COMMIT = "a" * 40


class _SourceMixin:
    def _source(self):
        return resolve_local(PACKAGE_ROOT, commit=TEST_COMMIT)


MANIFEST_VERSION = load_manifest(
    REPO_ROOT / "distribution" / "manifest.json"
)["distribution_version"]

STATE_JSON = {
    "schema_version": 1,
    "source": {"repository": "OasisSaber/TheMasterplan", "version": MANIFEST_VERSION, "commit": "a" * 40},
    "selection": {"profile": "jj", "validation_path": "scripts/check.sh", "default_branch": "main"},
    "managed_files": {},
    "adoption": {"date": "2026-08-02", "platform": "linux", "git_version": "2.40", "jj_version": "0.43", "status": "PARTIAL"},
}


def run_exec(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run themasterplan.py as a subprocess for CLI-level tests."""
    return subprocess.run(
        [sys.executable, str(EXECUTOR_DIR / "themasterplan.py"), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


class PathSafetyTest(unittest.TestCase):
    def test_rejects_parent_traversal(self) -> None:
        with self.assertRaises(PathSafetyError):
            safe_join(Path("/tmp/root"), "../escape")

    def test_rejects_absolute_path(self) -> None:
        with self.assertRaises(PathSafetyError):
            safe_join(Path("/tmp/root"), "/etc/passwd")

    def test_accepts_nested_safe(self) -> None:
        target = safe_join(Path("/tmp/root"), "core/policy.md")
        self.assertTrue(target.as_posix().endswith("core/policy.md"))


class ManifestTest(unittest.TestCase):
    def test_real_manifest_loads(self) -> None:
        manifest = load_manifest(PACKAGE_ROOT / "distribution" / "manifest.json")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertTrue(manifest["files"])

    def test_missing_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"files": []}', encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifest(path)

    def test_bad_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            data = dict(STATE_JSON)
            data["schema_version"] = 99
            data["files"] = [{"source": "a", "destination": "b", "ownership": "managed-replace"}]
            write_json_atomic(path, data)
            with self.assertRaises(ManifestError):
                load_manifest(path)

    def test_duplicate_destination_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            data = {
                "schema_version": 1,
                "distribution_version": "v1.0.0",
                "source_repository": "OasisSaber/TheMasterplan",
                "files": [
                    {"source": "x", "destination": "dup", "ownership": "managed-replace"},
                    {"source": "y", "destination": "dup", "ownership": "managed-replace"},
                ],
            }
            write_json_atomic(path, data)
            with self.assertRaises(ManifestError):
                load_manifest(path)

    def test_unsafe_destination_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            data = {
                "schema_version": 1,
                "distribution_version": "v1.0.0",
                "source_repository": "OasisSaber/TheMasterplan",
                "files": [{"source": "x", "destination": "../evil", "ownership": "managed-replace"}],
            }
            write_json_atomic(path, data)
            with self.assertRaises(ManifestError):
                load_manifest(path)


class InspectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_state(self, state: dict) -> None:
        # A complete simulated installation includes its selected VCS profile.
        profile = f"profiles/{state['selection']['profile']}.md"
        target = self.root / profile
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"selected profile\n")
        state["managed_files"][profile] = {
            "installed_sha256": sha256_of_file(target), "ownership": "managed-replace"}
        write_json_atomic(self.root / ".themasterplan/state.json", state)

    def test_absent_empty_dir(self) -> None:
        status, _ = detect_status(self.root)
        self.assertEqual(status, "ABSENT")

    def test_incomplete_partial_core(self) -> None:
        (self.root / "core").mkdir(parents=True)
        (self.root / "core/policy.md").write_text("x", encoding="utf-8")
        status, _ = detect_status(self.root)
        self.assertEqual(status, "INCOMPLETE")

    def test_broken_state(self) -> None:
        (self.root / ".themasterplan").mkdir(parents=True)
        (self.root / ".themasterplan/state.json").write_text("{not json", encoding="utf-8")
        status, _ = detect_status(self.root)
        self.assertEqual(status, "BROKEN")

    def test_current_after_adopt(self) -> None:
        # simulate a completed adoption: core files + matching state
        (self.root / "core").mkdir(parents=True)
        for name in ("policy.md", "workflow.md"):
            (self.root / "core" / name).write_text("body", encoding="utf-8")
        state = json.loads(json.dumps(STATE_JSON))
        state["managed_files"] = {
            "core/policy.md": {"installed_sha256": sha256_of_file(self.root / "core/policy.md"), "ownership": "managed-replace"},
            "core/workflow.md": {"installed_sha256": sha256_of_file(self.root / "core/workflow.md"), "ownership": "managed-replace"},
        }
        self._write_state(state)
        status, issues = detect_status(self.root)
        self.assertEqual(status, "CURRENT", issues)

    def test_modified_detected(self) -> None:
        (self.root / "core").mkdir(parents=True)
        for name in ("policy.md", "workflow.md"):
            (self.root / "core" / name).write_text("body", encoding="utf-8")
        state = json.loads(json.dumps(STATE_JSON))
        state["managed_files"] = {
            "core/policy.md": {"installed_sha256": "0" * 64, "ownership": "managed-replace"},
            "core/workflow.md": {"installed_sha256": sha256_of_file(self.root / "core/workflow.md"), "ownership": "managed-replace"},
        }
        self._write_state(state)
        status, issues = detect_status(self.root)
        self.assertEqual(status, "MODIFIED", issues)

    def test_outdated_when_target_differs(self) -> None:
        (self.root / "core").mkdir(parents=True)
        for name in ("policy.md", "workflow.md"):
            (self.root / "core" / name).write_text("body", encoding="utf-8")
        state = json.loads(json.dumps(STATE_JSON))
        state["managed_files"] = {
            "core/policy.md": {"installed_sha256": sha256_of_file(self.root / "core/policy.md"), "ownership": "managed-replace"},
            "core/workflow.md": {"installed_sha256": sha256_of_file(self.root / "core/workflow.md"), "ownership": "managed-replace"},
        }
        self._write_state(state)
        status, _ = detect_status(self.root, target_version="v9.9.9")
        self.assertEqual(status, "OUTDATED")

    def test_modified_precedes_outdated(self) -> None:
        """MODIFIED takes precedence over OUTDATED."""
        (self.root / "core").mkdir(parents=True)
        for name in ("policy.md", "workflow.md"):
            (self.root / "core" / name).write_text("body", encoding="utf-8")
        state = json.loads(json.dumps(STATE_JSON))
        state["managed_files"] = {
            "core/policy.md": {"installed_sha256": "0" * 64, "ownership": "managed-replace"},
            "core/workflow.md": {"installed_sha256": sha256_of_file(self.root / "core/workflow.md"), "ownership": "managed-replace"},
        }
        self._write_state(state)
        status, _ = detect_status(self.root, target_version="v9.9.9")
        self.assertEqual(status, "MODIFIED", "MODIFIED must win over OUTDATED")

    def test_detect_profile(self) -> None:
        (self.root / ".jj").mkdir()
        (self.root / ".trellis").mkdir()
        result = inspect(self.root)
        self.assertEqual(result["detected_profile"], "jj")
        self.assertNotIn("detected_adapter", result)


class AdoptFlowTest(_SourceMixin, unittest.TestCase):
    """End-to-end adopt against a temp (empty) git repo, real package."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(
            ["git", "init", "--initial-branch=main", "-q", str(self.root)],
            check=True,
            capture_output=True,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _plan(self, profile="git", validation="scripts/check.sh") -> dict:
        source = resolve_local(PACKAGE_ROOT, commit=TEST_COMMIT)
        return plan_adopt(
            self.root,
            source,
            profile=profile,
            validation_path=validation,
        )

    def test_empty_repo_full_adopt_then_idempotent(self) -> None:
        plan = self._plan()
        self.assertFalse(plan["stop_conditions"], plan["stop_conditions"])
        add_dests = [op["destination"] for op in plan["files"] if op["classification"] == "ADD"]
        self.assertIn("core/policy.md", add_dests)
        self.assertIn("core/workflow.md", add_dests)
        self.assertIn("AGENTS.md", add_dests)
        self.assertIn("scripts/check.sh", add_dests)
        self.assertIn(".github/workflows/check.yml", add_dests)
        self.assertNotIn("profiles/jj.md", add_dests)  # profile=git selected

        result = None  # apply via the real plan file below
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        applied = apply_adopt(self.root, plan_path, self._source())
        self.assertIn("core/policy.md", applied["written"])
        self.assertIn("AGENTS.md", applied["written"])
        self.assertTrue((self.root / "core/policy.md").is_file())
        self.assertTrue((self.root / ".themasterplan/state.json").is_file())
        self.assertTrue((self.root / ".themasterplan/bin/themasterplan.py").is_file())
        # AGENTS.md contains managed block markers
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- THEMASTERPLAN:BEGIN MANAGED -->", agents)
        self.assertIn("<!-- THEMASTERPLAN:END MANAGED -->", agents)

        # verify passes
        report = verify(self.root)
        self.assertTrue(report["ok"], report["issues"])

        # idempotent second apply: nothing re-written destructively
        applied2 = apply_adopt(self.root, plan_path, self._source())
        self.assertEqual(applied2["written"], [])
        self.assertEqual(applied2["unchanged"], applied["written"])

        # inspect now reports CURRENT
        status, issues = detect_status(self.root, target_version=MANIFEST_VERSION)
        self.assertEqual(status, "CURRENT", issues)

    def test_existing_agents_block_preserved_and_replaced(self) -> None:
        (self.root / "AGENTS.md").write_text(
            "PROJECT HEADER\n<!-- THEMASTERPLAN:BEGIN MANAGED -->old block<!-- THEMASTERPLAN:END MANAGED -->\nPROJECT FOOTER\n",
            encoding="utf-8",
        )
        plan = self._plan()
        agents_op = next(op for op in plan["files"] if op["destination"] == "AGENTS.md")
        self.assertEqual(agents_op["classification"], "BLOCK_PRESENT")
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        apply_adopt(self.root, plan_path, self._source())
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("PROJECT HEADER"))
        self.assertTrue(text.rstrip("\n").endswith("PROJECT FOOTER"))
        self.assertIn("# TheMasterplan", text)
        self.assertNotIn("old block", text)

    def test_agents_block_missing_stops(self) -> None:
        (self.root / "AGENTS.md").write_text("project-only content", encoding="utf-8")
        plan = self._plan()
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        with self.assertRaises(TheMasterplanError):
            apply_adopt(self.root, plan_path, self._source())
        self.assertFalse((self.root / ".themasterplan/state.json").exists())

    def test_validation_path_exists_kept(self) -> None:
        (self.root / "scripts").mkdir()
        (self.root / "scripts/check.sh").write_text("#!/bin/bash\necho custom\n", encoding="utf-8")
        plan = self._plan()
        check_op = next(op for op in plan["files"] if op["destination"] == "scripts/check.sh")
        self.assertEqual(check_op["classification"], "EXISTS_KEEP")
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        apply_adopt(self.root, plan_path, self._source())
        self.assertEqual(
            (self.root / "scripts/check.sh").read_text(encoding="utf-8"),
            "#!/bin/bash\necho custom\n",
            "existing validation entrypoint must not be overwritten",
        )

    def test_jj_profile_selection(self) -> None:
        plan = self._plan(profile="jj")
        dests = [op["destination"] for op in plan["files"]]
        self.assertIn("profiles/jj.md", dests)
        self.assertNotIn("profiles/git.md", dests)
        self.assertFalse(any(dest.startswith("adapters/") for dest in dests))


    def test_invalid_commit_assertion_fails(self) -> None:
        """The resolver must reject a commit that is not a full 40-char SHA."""
        with self.assertRaises(Exception) as ctx:
            resolve_local(PACKAGE_ROOT, commit="not-a-sha")
        self.assertIn("40-char lowercase SHA", str(ctx.exception))

    def test_block_outside_change_keeps_current(self) -> None:
        """Editing AGENTS.md outside the managed block keeps CURRENT/verify OK."""
        plan = self._plan()
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        apply_adopt(self.root, plan_path, self._source())
        # Project content outside the block (project facts section).
        # Use write_bytes to avoid platform newline conversion changing
        # byte-level hashes of the untouched block.
        agents = self.root / "AGENTS.md"
        agents.write_bytes(agents.read_bytes() + b"\n- \xe9\xa1\xb9\xe7\x9b\xae\xe5\x90\x8d: Demo\n")
        status, issues = detect_status(self.root, target_version=MANIFEST_VERSION)
        self.assertEqual(status, "CURRENT", issues)
        report = verify(self.root)
        self.assertTrue(report["ok"], report["issues"])

    def test_block_inside_change_marks_modified(self) -> None:
        """Editing inside the managed block returns MODIFIED and verify fails."""
        plan = self._plan()
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        apply_adopt(self.root, plan_path, self._source())
        agents = self.root / "AGENTS.md"
        data = agents.read_bytes()
        agents.write_bytes(
            data.replace(
                b"This block is the project Context Router.",
                b"This block is the modified Context Router.",
                1,
            )
        )
        status, issues = detect_status(self.root, target_version=MANIFEST_VERSION)
        self.assertEqual(status, "MODIFIED", issues)
        report = verify(self.root)
        self.assertFalse(report["ok"], "verify must fail when block is modified")

    def test_target_changed_after_plan_stops(self) -> None:
        """Apply must refuse when an observed managed target changed after planning."""
        # Pre-install a file identical to the package source so it plans as
        # UNCHANGED with an observed hash.
        (self.root / "core").mkdir(parents=True)
        source_content = read_package_file(PACKAGE_ROOT, "core/workflow.md")
        (self.root / "core/workflow.md").write_bytes(source_content)
        plan = self._plan()
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        # Modify the target after planning.
        (self.root / "core/workflow.md").write_text("tampered after plan\n", encoding="utf-8")
        with self.assertRaises(TheMasterplanError) as ctx:
            apply_adopt(self.root, plan_path, self._source())
        self.assertIn("changed since plan", str(ctx.exception))
        self.assertFalse((self.root / ".themasterplan/state.json").exists(), "nothing may be written")

    def test_source_changed_after_plan_stops(self) -> None:
        """Apply must refuse when the package source file changed after planning."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp)
            for sub in ("distribution", "core", "profiles", "skills"):
                shutil.copytree(PACKAGE_ROOT / sub, pkg / sub)
            plan = plan_adopt(
                self.root,
                resolve_local(pkg, commit=TEST_COMMIT),
                profile="git",
                validation_path="scripts/check.sh",
            )
            plan_path = self.root / ".themasterplan-plan.json"
            write_json_atomic(plan_path, plan)
            # Tamper with the package source after planning.
            (pkg / "core" / "workflow.md").write_bytes(b"tampered package\n")
            with self.assertRaises(TheMasterplanError) as ctx:
                apply_adopt(self.root, plan_path, resolve_local(pkg, commit=TEST_COMMIT))
            self.assertIn("source file changed since plan", str(ctx.exception))
            self.assertFalse((self.root / ".themasterplan/state.json").exists())

    def test_late_source_changed_stops_before_any_write(self) -> None:
        """A later selected source mismatch must fail before any project write."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp)
            for sub in ("distribution", "core", "profiles", "skills"):
                shutil.copytree(PACKAGE_ROOT / sub, pkg / sub)
            plan = plan_adopt(
                self.root,
                resolve_local(pkg, commit=TEST_COMMIT),
                profile="git",
                validation_path="scripts/check.sh",
            )
            plan_path = self.root / ".themasterplan-plan.json"
            write_json_atomic(plan_path, plan)
            (pkg / "profiles" / "git.md").write_bytes(b"tampered later source\n")
            with self.assertRaises(TheMasterplanError) as ctx:
                apply_adopt(
                    self.root,
                    plan_path,
                    resolve_local(pkg, commit=TEST_COMMIT),
                )
            self.assertIn("source file changed since plan", str(ctx.exception))
            self.assertFalse((self.root / "core" / "workflow.md").exists())
            self.assertFalse((self.root / "core" / "policy.md").exists())
            self.assertFalse((self.root / "profiles" / "git.md").exists())
            self.assertFalse((self.root / "AGENTS.md").exists())
            self.assertFalse(
                (self.root / ".themasterplan" / "state.json").exists()
            )

    def test_custom_default_branch_rendered(self) -> None:
        """The consumer workflow must target the selected default branch."""
        manifest = load_manifest(PACKAGE_ROOT / "distribution" / "manifest.json")
        plan = plan_adopt(
            self.root,
            self._source(),
            profile="git",
            validation_path="scripts/check.sh",
            default_branch="master",
        )
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        apply_adopt(self.root, plan_path, self._source())
        workflow = (self.root / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")
        self.assertEqual(workflow.count('branches: ["master"]'), 2)
        self.assertNotIn("branches: [main]", workflow)
        state = json.loads((self.root / ".themasterplan" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["selection"]["default_branch"], "master")

    def test_custom_validation_path(self) -> None:
        """Custom validation path: rendered into the workflow, no default check.sh."""
        plan = self._plan(validation="tools/verify.sh")
        dests = [op["destination"] for op in plan["files"]]
        self.assertIn("tools/verify.sh", dests)
        self.assertNotIn("scripts/check.sh", dests, "default check.sh must not be installed")
        plan_path = self.root / ".themasterplan-plan.json"
        write_json_atomic(plan_path, plan)
        apply_adopt(self.root, plan_path, self._source())
        workflow = (self.root / ".github/workflows/check.yml").read_text(encoding="utf-8")
        self.assertIn('project-check-path: "tools/verify.sh"', workflow)
        self.assertTrue((self.root / "tools/verify.sh").is_file())
        report = verify(self.root)
        self.assertTrue(report["ok"], report["issues"])


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_inspect_cli_absent(self) -> None:
        proc = run_exec(["inspect", "--root", str(self.root)], self.root)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "ABSENT")

    def test_plan_apply_verify_cli_roundtrip(self) -> None:
        plan_out = self.root / "plan.json"
        manifest = load_manifest(PACKAGE_ROOT / "distribution" / "manifest.json")
        proc = run_exec(
            [
                "plan-adopt",
                "--root", str(self.root),
                "--source", str(PACKAGE_ROOT),
                "--commit", TEST_COMMIT,
                "--profile", "git",
                "--validation-path", "scripts/check.sh",
                "--output", str(plan_out),
            ],
            self.root,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(plan_out.is_file())
        apply_proc = run_exec(
            ["apply-adopt", "--root", str(self.root), "--plan", str(plan_out),
             "--plan-sha256", json.loads(plan_out.read_text())["plan_sha256"],
             "--source", str(PACKAGE_ROOT), "--commit", TEST_COMMIT],
            self.root,
        )
        self.assertEqual(apply_proc.returncode, 0, apply_proc.stderr)
        verify_proc = run_exec(["verify", "--root", str(self.root)], self.root)
        self.assertEqual(verify_proc.returncode, 0, verify_proc.stderr)


class PlanAdoptParserTest(unittest.TestCase):
    """v5 plan-adopt has no Adapter CLI surface."""

    def test_plan_adopt_has_no_adapter_argument(self):
        parser = build_parser()
        common = [
            "plan-adopt",
            "--source",
            ".",
            "--profile",
            "git",
            "--validation-path",
            "scripts/check.sh",
            "--output",
            "plan.json",
        ]

        args = parser.parse_args(common)
        self.assertFalse(hasattr(args, "adapter"))

        with self.assertRaises(SystemExit):
            parser.parse_args(common + ["--adapter", "generic"])


class AdoptSafetyTests(unittest.TestCase):
    """Run the actual adoption transaction; refusal must preserve every byte."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)
        self.root = self.workspace / "project"
        self.root.mkdir()
        self.package = self.workspace / "package"
        for part in ("core", "profiles", "distribution", "skills/themasterplan"):
            shutil.copytree(PACKAGE_ROOT / part, self.package / part,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.source = resolve_local(self.package, commit=TEST_COMMIT)
        self.plan_path = self.workspace / "plan.json"

    def plan(self, profile="git"):
        return plan_adopt(self.root, self.source, profile=profile,
                          validation_path="scripts/check.sh")

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}

    def apply(self, plan, **kwargs):
        write_json_atomic(self.plan_path, plan)
        return apply_adopt(self.root, self.plan_path, self.source, **kwargs)

    def refused(self, plan, **kwargs):
        before = self.snapshot()
        with self.assertRaises(TheMasterplanError):
            self.apply(plan, **kwargs)
        self.assertEqual(before, self.snapshot())

    def test_full_bundle_is_planned_and_written_for_both_profiles(self):
        for profile in ("git", "jj"):
            with self.subTest(profile=profile):
                self.root = self.workspace / profile
                self.root.mkdir()
                plan = self.plan(profile)
                bundle = {f".themasterplan/bin/{p}" for p in EXECUTOR_FILES}
                self.assertTrue(bundle <= {op["destination"] for op in plan["files"]})
                before = self.snapshot()
                result = self.apply(plan)
                actual = {p for p, data in self.snapshot().items() if before.get(p) != data}
                self.assertEqual(actual - {".themasterplan/state.json"}, set(result["written"]))
                self.assertTrue(verify(self.root)["ok"])
                self.assertEqual(self.apply(plan)["written"], [])

    def test_unregistered_executor_never_overwritten_even_when_matching(self):
        path = ".themasterplan/bin/tmlib/apply.py"
        target = self.root / path
        target.parent.mkdir(parents=True)
        for data in (b"# local patch\n", (self.package / "skills/themasterplan/scripts/tmlib/apply.py").read_bytes()):
            with self.subTest(data=data[:20]):
                target.write_bytes(data)
                plan = self.plan()
                self.assertIn(path, {op["destination"] for op in plan["files"]})
                self.assertTrue(plan["stop_conditions"])
                self.refused(plan)

    def test_recomputed_summary_cannot_authorize_forged_operations(self):
        original = self.plan()
        mutations = [
            lambda p: p["files"].append({**p["files"][0], "destination": "extra.md"}),
            lambda p: p["files"].pop(),
        ]
        for key, value in (("ownership", "generated-if-missing"), ("source", "core/policy.md"),
                           ("required", False), ("render", True), ("source_sha256", None),
                           ("classification", "PROJECT_OWNED"), ("target_sha256", "0" * 64)):
            mutations.append(lambda p, k=key, v=value: p["files"][0].update({k: v}))
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                plan = copy.deepcopy(original)
                mutate(plan)
                plan["plan_sha256"] = adopt_plan_digest(plan)
                self.refused(plan)

    def test_review_summary_binds_selection_even_when_canonical(self):
        original = self.plan()
        changed = plan_adopt(self.root, self.source, profile="git",
                             validation_path="tools/check.sh", default_branch="master")
        self.refused(changed, reviewed_plan_sha256=original["plan_sha256"])

    def test_missing_summary_is_rejected(self):
        plan = self.plan()
        del plan["plan_sha256"]
        self.refused(plan)

    def test_cli_requires_the_reviewed_summary(self):
        plan = self.plan()
        write_json_atomic(self.plan_path, plan)
        args = ["apply-adopt", "--root", str(self.root), "--plan", str(self.plan_path),
                "--source", str(self.package), "--commit", TEST_COMMIT]
        before = self.snapshot()
        for tail in ([], ["--plan-sha256", "0" * 64]):
            result = run_exec(args + tail, self.root)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, self.snapshot())

    def test_unplanned_executor_source_drift_stops_before_all_writes(self):
        plan = self.plan()
        target = self.package / "skills/themasterplan/scripts/tmlib/apply.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        self.refused(plan)

    def test_manifest_drift_stops_before_all_writes(self):
        plan = self.plan()
        manifest = self.package / "distribution/manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        self.refused(plan)

    def test_complete_block_retry_keeps_project_content_and_detects_drift(self):
        target = self.root / "AGENTS.md"
        target.write_bytes(b"header\r\n<!-- THEMASTERPLAN:BEGIN MANAGED -->old<!-- THEMASTERPLAN:END MANAGED -->\r\nfooter")
        plan = self.plan()
        self.apply(plan)
        before = self.snapshot()
        self.assertEqual(self.apply(plan)["written"], [])
        self.assertEqual(before, self.snapshot())
        target.write_bytes(target.read_bytes() + b"\nproject-owned addition")
        self.assertEqual(self.apply(plan)["written"], [])
        target.write_bytes(target.read_bytes().replace(b"This block is", b"Tampered block is"))
        self.refused(plan)

    def test_regenerated_adoption_and_broken_installation_are_refused(self):
        original = self.plan()
        self.apply(original)
        self.refused(self.plan())
        (self.root / ".themasterplan/bin/tmlib/apply.py").unlink()
        self.refused(original)
        (self.root / ".themasterplan/state.json").write_bytes(b"{broken")
        self.refused(original)

    def test_caught_late_write_failure_rolls_back_adoption(self):
        from tmlib import util
        plan = self.plan()
        real_write = util.write_bytes_atomic
        count = 0

        def fail_once(path, content, **kwargs):
            nonlocal count
            count += 1
            if count == 4:
                raise OSError("injected failure")
            return real_write(path, content, **kwargs)

        write_json_atomic(self.plan_path, plan)
        before = self.snapshot()
        with mock.patch("tmlib.util.write_bytes_atomic", side_effect=fail_once):
            with self.assertRaises(TheMasterplanError):
                apply_adopt(self.root, self.plan_path, self.source)
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
