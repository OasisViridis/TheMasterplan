"""Issue #103: skill guidance through public adoption/update/diagnostic commands."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "skills/themasterplan/scripts/themasterplan.py"
REFERENCE = "core/skill-collaboration.md"
FIXTURE_COMMIT = "a" * 40


class SkillCollaborationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.create_project("project")

    def create_project(self, name: str) -> None:
        self.root = Path(self.temporary.name) / name
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True,
                       capture_output=True)

    def command(self, command: str, *arguments: str, success: bool = True) -> dict:
        result = subprocess.run(
            [sys.executable, str(CLI), command, "--root", str(self.root), *arguments],
            capture_output=True, text=True, encoding="utf-8",
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout) if result.stdout else {"error": result.stderr}

    def package_copy(self, name: str) -> Path:
        package = Path(self.temporary.name) / name
        for relative in ("core", "profiles", "distribution", "skills"):
            shutil.copytree(ROOT / relative, package / relative,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return package

    def legacy_package(self) -> Path:
        """Model the pre-feature file set; exact released-source smoke is separate."""
        package = self.package_copy("legacy")
        manifest_path = package / "distribution/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["required"].remove(REFERENCE)
        manifest["files"] = [entry for entry in manifest["files"]
                             if entry["destination"] != REFERENCE]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (package / REFERENCE).unlink()
        # The old router does not advertise the new, unavailable guidance.
        for relative in ("distribution/templates/agents-managed-block.md",
                         "core/workflow.md"):
            path = package / relative
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            path.write_text("".join(line for line in lines if REFERENCE not in line),
                            encoding="utf-8")
        return package

    def plan_update(self) -> dict:
        self.plan_path = Path(self.temporary.name) / "update.json"
        return self.command("plan-update", "--source", str(ROOT), "--commit",
                            "b" * 40, "--output", str(self.plan_path))

    def apply_update(self, success: bool = True) -> dict:
        return self.command("apply-update", "--source", str(ROOT), "--commit",
                            "b" * 40, "--plan", str(self.plan_path), success=success)

    def plan_adopt(self, profile: str = "git", source: Path = ROOT) -> dict:
        self.plan_path = Path(self.temporary.name) / "adopt.json"
        return self.command("plan-adopt", "--source", str(source), "--commit",
                            FIXTURE_COMMIT, "--profile", profile,
                            "--validation-path", "scripts/check.sh",
                            "--output", str(self.plan_path))

    def adopt(self, profile: str = "git", source: Path = ROOT) -> dict:
        plan = self.plan_adopt(profile, source)
        self.assertEqual(plan["stop_conditions"], [])
        self.command("apply-adopt", "--source", str(source), "--commit",
                     FIXTURE_COMMIT, "--plan", str(self.plan_path))
        return plan

    def test_git_and_jj_adopt_install_reachable_required_guidance(self) -> None:
        for profile in ("git", "jj"):
            with self.subTest(profile=profile):
                self.create_project(profile)
                plan = self.adopt(profile)
                operations = {op["destination"]: op for op in plan["files"]}
                self.assertIn(REFERENCE, operations)
                operation = operations[REFERENCE]
                self.assertTrue(operation["required"])
                self.assertEqual(operation["ownership"], "managed-replace")
                self.assertEqual((self.root / REFERENCE).read_bytes(),
                                 (ROOT / REFERENCE).read_bytes())
                for relative in ("AGENTS.md", "core/workflow.md"):
                    self.assertIn(REFERENCE, (self.root / relative).read_text(encoding="utf-8"))
                self.assertTrue(self.command("verify")["ok"])

    def test_selection_rejects_missing_required_mapping_or_source(self) -> None:
        for mutation in ("mapping", "ownership", "source"):
            with self.subTest(mutation=mutation):
                package = self.package_copy(mutation)
                path = package / "distribution/manifest.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if mutation == "mapping":
                    manifest["files"] = [entry for entry in manifest["files"]
                                         if entry["destination"] != REFERENCE]
                elif mutation == "ownership":
                    entry = next(entry for entry in manifest["files"]
                                 if entry["destination"] == REFERENCE)
                    entry["ownership"] = "project-owned"
                else:
                    (package / REFERENCE).unlink()
                path.write_text(json.dumps(manifest), encoding="utf-8")
                result = self.command("plan-adopt", "--source", str(package),
                                      "--commit", FIXTURE_COMMIT, "--profile", "git",
                                      "--validation-path", "scripts/check.sh",
                                      "--output", str(package / "plan.json"), success=False)
                self.assertIn("requires managed mapping" if mutation != "source"
                              else "source missing", result["error"])
                self.assertFalse((package / "plan.json").exists())

    def test_adopt_stops_at_same_name_local_conflict(self) -> None:
        target = self.root / REFERENCE
        target.parent.mkdir()
        target.write_text("Project-owned guidance\n", encoding="utf-8")
        plan = self.plan_adopt()
        operation = next(op for op in plan["files"] if op["destination"] == REFERENCE)
        self.assertTrue(operation["required"])
        self.assertEqual(operation["classification"], "CONFLICT")
        self.assertTrue(plan["stop_conditions"])
        self.command("apply-adopt", "--source", str(ROOT), "--commit", FIXTURE_COMMIT,
                     "--plan", str(self.plan_path), success=False)
        self.assertEqual(target.read_text(encoding="utf-8"), "Project-owned guidance\n")
        self.assertFalse((self.root / ".themasterplan/state.json").exists())

    def test_legacy_upgrade_adds_guidance_and_preserves_project_router(self) -> None:
        legacy = self.legacy_package()
        for profile in ("git", "jj"):
            with self.subTest(profile=profile):
                self.create_project("upgrade-" + profile)
                self.adopt(profile, legacy)
                self.assertFalse((self.root / REFERENCE).exists())
                # Candidate diagnostics must still accept the historical file set.
                self.assertTrue(self.command("verify")["ok"])
                self.assertTrue(self.command("doctor")["ok"])
                router = self.root / "AGENTS.md"
                router.write_text("User router before\n" + router.read_text(encoding="utf-8")
                                  + "\nUser router after\n", encoding="utf-8")
                plan = self.plan_update()
                operation = next(op for op in plan["files"] if op["destination"] == REFERENCE)
                self.assertEqual(operation["classification"], "ADD")
                self.assertTrue(operation["required"])
                self.assertEqual(plan["stop_conditions"], [])
                self.assertFalse((self.root / REFERENCE).exists(), "planning must not apply")
                self.apply_update()
                self.assertEqual((self.root / REFERENCE).read_bytes(), (ROOT / REFERENCE).read_bytes())
                state = json.loads((self.root / ".themasterplan/state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["managed_files"][REFERENCE]["ownership"], "managed-replace")
                self.assertTrue(router.read_text(encoding="utf-8").startswith("User router before\n"))
                self.assertTrue(router.read_text(encoding="utf-8").endswith("\nUser router after\n"))
                self.assertIn(REFERENCE, router.read_text(encoding="utf-8"))
                self.assertTrue(self.command("verify")["ok"])

    def test_upgrade_conflict_and_changed_plan_cannot_apply(self) -> None:
        self.adopt(source=self.legacy_package())
        plan = self.plan_update()
        original_plan = self.plan_path.read_bytes()
        plan["files"] = [op for op in plan["files"] if op["destination"] != REFERENCE]
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        self.assertIn("plan differs", self.apply_update(success=False)["error"])
        self.assertFalse((self.root / REFERENCE).exists())
        self.plan_path.write_bytes(original_plan)
        target = self.root / REFERENCE
        target.write_text("Local customization\n", encoding="utf-8")
        self.apply_update(success=False)
        plan = self.plan_update()
        operation = next(op for op in plan["files"] if op["destination"] == REFERENCE)
        self.assertEqual(operation["classification"], "LOCAL_MODIFIED")
        self.assertTrue(plan["stop_conditions"])
        self.apply_update(success=False)
        self.assertEqual(target.read_text(encoding="utf-8"), "Local customization\n")

    def test_registered_guidance_missing_or_drift_is_diagnosed_and_blocks_update(self) -> None:
        for mutation in ("missing", "drift"):
            with self.subTest(mutation=mutation):
                self.create_project(mutation)
                self.adopt()
                target = self.root / REFERENCE
                if mutation == "missing":
                    target.unlink()
                else:
                    target.write_text("Locally edited guidance\n", encoding="utf-8")
                for command in ("verify", "doctor"):
                    result = self.command(command, success=False)
                    self.assertFalse(result["ok"])
                    prefix = ("missing" if mutation == "missing" else "hash mismatch")
                    self.assertTrue(any(issue.startswith(prefix) and REFERENCE in issue
                                        for issue in result["issues"]), result["issues"])
                inspection = self.command("inspect", success=False)
                self.assertEqual(inspection["status"],
                                 "BROKEN" if mutation == "missing" else "MODIFIED")
                plan = self.plan_update()
                operation = next(op for op in plan["files"] if op["destination"] == REFERENCE)
                self.assertEqual(operation["classification"], "LOCAL_MODIFIED")
                self.assertTrue(plan["stop_conditions"])
                self.apply_update(success=False)


if __name__ == "__main__":
    unittest.main()
