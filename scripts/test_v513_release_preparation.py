"""Version identity and truthful pre-publication contracts for v5.1.3."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
VERSION = "v5.1.3"
PREVIOUS = "v5.1.2"


class ReleasePreparationTests(unittest.TestCase):
    def test_manifest_target_version(self):
        manifest = json.loads((ROOT / "distribution/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["distribution_version"], VERSION)
        self.assertEqual(manifest["schema_version"], 1)

    def test_consumer_template_pair_and_publication_guard(self):
        text = (ROOT / "distribution/templates/consumer-workflow.yml").read_text(encoding="utf-8")
        self.assertIn("themasterplan-check.yml@" + VERSION, text)
        self.assertIn("policy-ref: " + VERSION, text)
        self.assertIn("Tag", text)
        self.assertIn("发布", text)

    def test_current_examples_and_release_status_are_explicit(self):
        for relative in ("README.md", "docs/actions-interface.md", "docs/adoption-guide.md", "docs/release-channels.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("themasterplan-check.yml@" + VERSION, text)
                self.assertIn("policy-ref: " + VERSION, text)
                self.assertIn("发布状态", text)
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("themasterplan-check.yml@" + VERSION, agents)
        self.assertIn("发布状态", agents)

    def test_release_notes_document_upgrade_limits_and_sources(self):
        notes = (ROOT / f"docs/releases/{VERSION}.md").read_text(encoding="utf-8")
        for required in (VERSION, "发布状态", PREVIOUS, "停止", "v1", "未验证", "受管", "采纳项目"):
            self.assertIn(required, notes)
        self.assertIn(
            "https://github.com/OasisViridis/TheMasterplan/pull/119",
            notes,
        )

    def test_release_notes_do_not_overclaim_unverified_behaviour_acceptance(self):
        notes = (ROOT / f"docs/releases/{VERSION}.md").read_text(encoding="utf-8")
        self.assertIn("未验证", notes)
        self.assertNotIn("行为场景已完成", notes)
        # The prior release notes remain a published reference.
        previous = (ROOT / f"docs/releases/{PREVIOUS}.md").read_text(encoding="utf-8")
        self.assertIn(f"# {PREVIOUS} 发布说明", previous)

    def test_skill_collaboration_reference_is_registered_and_distributed(self):
        manifest = json.loads((ROOT / "distribution/manifest.json").read_text(encoding="utf-8"))
        entries = [
            entry
            for entry in manifest["files"]
            if entry["destination"] == "core/skill-collaboration.md"
        ]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["ownership"], "managed-replace")
        self.assertTrue(entries[0]["required"])
        self.assertIn("core/skill-collaboration.md", manifest["required"])
        self.assertTrue((ROOT / "core/skill-collaboration.md").is_file())

    def test_boundary_notes_do_not_freeze_prepublication_status(self):
        text = (ROOT / "docs/client-update-flow.md").read_text(encoding="utf-8")
        self.assertIn("## v5.1.0 边界加固（PR #100）", text)
        self.assertIn("发布状态以 v5.1.0 Release", text)
        self.assertNotIn("这些改动尚未发布", text)

    def test_frozen_compatibility_and_published_baseline_remain_documented(self):
        channels = (ROOT / "docs/release-channels.md").read_text(encoding="utf-8")
        self.assertIn(f"{VERSION}      本源码目标不可变 Release tag", channels)
        self.assertIn(f"{PREVIOUS}      历史不可变 Release tag", channels)
        self.assertIn("v5.1.1      历史不可变 Release tag", channels)
        self.assertIn("v5.1.0      历史不可变 Release tag", channels)
        self.assertIn("v5.0.0      历史不可变 Release tag", channels)
        self.assertIn("v1", channels)
        self.assertIn("冻结", channels)
        self.assertIn("aw-check.yml@v1", channels)


if __name__ == "__main__":
    unittest.main()
