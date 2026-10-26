import re
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

try:
    from scripts.test_check_entry import BASH
except ModuleNotFoundError:  # direct execution: sys.path[0] is scripts/
    from test_check_entry import BASH

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/themasterplan-check.yml"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class StringKeyLoader(yaml.SafeLoader):
    pass


StringKeyLoader.add_implicit_resolver(
    "tag:yaml.org,2002:str",
    re.compile(r"^(?:on|off|yes|no|true|false|y|n)$", re.IGNORECASE),
    list("onOffyesfTRUEYN"),
)


def load_workflow():
    data = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=StringKeyLoader)
    if True in data:
        data["on"] = data.pop(True)
    return data


class ActionsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = load_workflow()
        cls.check = cls.workflow["jobs"]["check"]
        cls.checkout_steps = [
            step
            for step in cls.check["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        ]
        cls.step_sources = [
            step.get("uses", "")
            for step in cls.check["steps"]
            if step.get("uses")
        ]

    def test_workflow_call_trigger(self):
        self.assertIn("workflow_call", self.workflow["on"])

    def test_job_id_is_check(self):
        self.assertIn("check", self.workflow["jobs"])

    def test_job_name_is_check(self):
        self.assertEqual(self.check.get("name"), "check")

    def test_top_level_permissions_read_only(self):
        self.assertEqual(
            self.workflow.get("permissions", {}).get("contents"), "read"
        )
        self.assertEqual(len(self.workflow["permissions"]), 1)

    def test_no_pull_request_target(self):
        self.assertNotIn("pull_request_target", self.workflow.get("on", {}))

    def test_no_secrets_inherit(self):
        self.assertNotIn("secrets", self.workflow)
        for job in self.workflow["jobs"].values():
            self.assertNotIn("secrets", job)

    def test_no_write_all(self):
        self.assertNotEqual(self.workflow.get("permissions"), "write-all")

    def test_no_write_permissions(self):
        permissions = self.workflow.get("permissions", {})
        for name, value in permissions.items():
            self.assertNotEqual(value, "write")
        for job in self.workflow["jobs"].values():
            job_permissions = job.get("permissions", {})
            for name, value in job_permissions.items():
                self.assertNotEqual(value, "write")

    def test_checkout_persist_credentials_false(self):
        self.assertTrue(self.checkout_steps, "no checkout steps found")
        for step in self.checkout_steps:
            self.assertEqual(
                step.get("with", {}).get("persist-credentials"), False
            )

    def test_third_party_actions_pinned_to_full_sha(self):
        self.assertTrue(self.step_sources, "no action steps found")
        for source in self.step_sources:
            reference = source.split("@", 1)[1]
            self.assertRegex(reference, FULL_SHA)

    def test_default_project_check_path(self):
        self.assertEqual(
            self.workflow["on"]["workflow_call"]["inputs"]["project-check-path"][
                "default"
            ],
            "scripts/check.sh",
        )

    def test_default_policy_ref(self):
        self.assertEqual(
            self.workflow["on"]["workflow_call"]["inputs"]["policy-ref"]["default"],
            "v1",
        )

    def test_timeout_not_above_fifteen_minutes(self):
        self.assertLessEqual(self.check.get("timeout-minutes", 15), 15)

    def test_caller_path_is_project(self):
        paths = [
            step.get("with", {}).get("path")
            for step in self.checkout_steps
            if step.get("with", {}).get("path")
        ]
        self.assertIn("project", paths)
        self.assertEqual(paths[0], "project")

    def test_policy_path_is_themasterplan(self):
        paths = [
            step.get("with", {}).get("path")
            for step in self.checkout_steps
            if step.get("with", {}).get("path")
        ]
        self.assertIn(".themasterplan", paths)

    def test_runner_is_ubuntu_latest(self):
        self.assertEqual(self.check.get("runs-on"), "ubuntu-latest")

    def test_policy_selection_matches_repository_id_instead_of_names(self):
        steps = self.check["steps"]
        checkout = next(s for s in steps if s["name"] == "Checkout TheMasterplan policy")
        selection = next(s for s in steps if s["name"] == "Select policy source")
        self.assertEqual(checkout["if"], "github.repository_id != '1309061768'")
        self.assertEqual(checkout["with"]["repository"], "OasisViridis/TheMasterplan")
        self.assertEqual(checkout["with"]["ref"], "${{ inputs.policy-ref }}")
        # Both the workflow step env and the shared literal must stay wired.
        self.assertEqual(selection["env"]["POLICY_REF"], "${{ inputs.policy-ref }}")
        self.assertIn("1309061768", checkout["if"])
        self.assertIn("1309061768", selection["run"])
        # The ID is stable across renames; a same-name third-party repo is not self.
        cases = (
            ("1309061768", "OasisViridis/TheMasterplan", "project", "candidate"),
            ("1309061768", "renamed/Anything", "project", "candidate"),
            ("42", "OasisSaber/TheMasterplan", ".themasterplan", "central:v1"),
            ("42", "consumer/App", ".themasterplan", "central:v1"),
            ("42", "other/TheMasterplan", ".themasterplan", "central:v1"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for repository_id, repository, suffix, source in cases:
                with self.subTest(repository_id=repository_id, repository=repository):
                    env_file = Path(tmp) / "env"
                    env_file.write_bytes(b"")
                    env = {**os.environ, "GITHUB_REPOSITORY": repository,
                           "GITHUB_REPOSITORY_ID": repository_id,
                           "GITHUB_WORKSPACE": "/candidate", "GITHUB_ENV": env_file.as_posix(),
                           "POLICY_REF": "v1"}
                    result = subprocess.run([BASH, "-c", selection["run"]], env=env,
                                            capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    lines = env_file.read_text(encoding="utf-8").splitlines()
                    self.assertIn(f"POLICY_DIR=/candidate/{suffix}", lines)
                    self.assertIn(f"POLICY_SOURCE={source}", lines)

    def test_check_summary_reports_policy_source_without_stale_ref(self):
        steps = self.check["steps"]
        summary = next(s for s in steps if s["name"] == "Write check summary")
        self.assertEqual(summary["env"]["POLICY_SOURCE"], "${{ env.POLICY_SOURCE }}")
        self.assertEqual(summary["env"]["POLICY_REF"], "${{ inputs.policy-ref }}")
        cases = (("candidate", False), ("central:v1", True))
        with tempfile.TemporaryDirectory() as tmp:
            for source, expects_ref in cases:
                with self.subTest(policy_source=source):
                    out = Path(tmp) / "summary"
                    out.write_bytes(b"")
                    env = {**os.environ, "GITHUB_REPOSITORY": "caller/App",
                           "GITHUB_STEP_SUMMARY": out.as_posix(),
                           "POLICY_SOURCE": source, "POLICY_REF": "v1",
                           "PROJECT_CHECK_PATH": "scripts/check.sh"}
                    result = subprocess.run([BASH, "-c", summary["run"]], env=env,
                                            capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    text = out.read_text(encoding="utf-8")
                    self.assertIn(f"- Policy source: `{source}`", text)
                    self.assertIn("- Caller: `caller/App`", text)
                    self.assertEqual("Policy ref" in text, expects_ref)

    def test_selection_to_summary_chain_propagates_policy_source(self):
        steps = self.check["steps"]
        selection = next(s for s in steps if s["name"] == "Select policy source")
        summary = next(s for s in steps if s["name"] == "Write check summary")
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "env"
            env_file.write_bytes(b"")
            env = {**os.environ, "GITHUB_REPOSITORY": "OasisViridis/TheMasterplan",
                   "GITHUB_REPOSITORY_ID": "1309061768",
                   "GITHUB_WORKSPACE": "/candidate", "GITHUB_ENV": env_file.as_posix(),
                   "POLICY_REF": "v1"}
            result = subprocess.run([BASH, "-c", selection["run"]], env=env,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = dict(line.split("=", 1)
                          for line in env_file.read_text(encoding="utf-8").splitlines())
            out = Path(tmp) / "summary"
            out.write_bytes(b"")
            env = {**os.environ, "GITHUB_REPOSITORY": "OasisViridis/TheMasterplan",
                   "GITHUB_STEP_SUMMARY": out.as_posix(),
                   "POLICY_SOURCE": values["POLICY_SOURCE"],
                   "POLICY_REF": values.get("POLICY_REF", ""),
                   "PROJECT_CHECK_PATH": "scripts/check.sh"}
            result = subprocess.run([BASH, "-c", summary["run"]], env=env,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = out.read_text(encoding="utf-8")
            self.assertEqual(values["POLICY_SOURCE"], "candidate")
            self.assertIn("- Policy source: `candidate`", text)
            self.assertNotIn("Policy ref", text)

    def test_live_docs_do_not_reference_renamed_owner_workflows(self):
        root = Path(__file__).resolve().parent.parent
        tracked = subprocess.run(
            ["git", "ls-files", "--", "*.md", "*.yml", "*.yaml"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout.splitlines()
        offenders = []
        for relative in tracked:
            if relative.startswith("docs/releases/"):
                continue  # published release snapshots are immutable history
            path = root / relative
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                if "OasisSaber/" in line and "/.github/workflows/" in line:
                    offenders.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
