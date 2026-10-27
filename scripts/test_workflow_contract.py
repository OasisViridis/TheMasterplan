#!/usr/bin/env python3
"""Contract tests for the weak-model entry of the delivery workflow.

The 开工检查 table, the four human gates, the four-line delivery report and the
ambiguity rule are the parts a weaker model must not silently drop when it edits
the rule stack. Each assertion repeats on every surface that carries the rule:
the repository router, Core workflow, Core policy, the consumer managed block
and both skill entrypoints.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

AGENTS = ROOT / "AGENTS.md"
WORKFLOW = ROOT / "core/workflow.md"
POLICY = ROOT / "core/policy.md"
MANAGED_BLOCK = ROOT / "distribution/templates/agents-managed-block.md"
SKILL = ROOT / "skills/themasterplan/SKILL.md"
OPENCODE_SKILL = ROOT / ".opencode/skills/themasterplan/SKILL.md"

HUMAN_GATES = ("合并", "发布", "破坏性清理", "数据外发")
OPEN_CHECK_ROWS = ("任务来源", "工作区", "范围", "验证入口")
FOUR_LINES = ("改了哪些文件", "验证命令与最后结论", "PR 链接", "未完成项与缺口")


class WorkflowEntryContractTests(unittest.TestCase):
    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_open_check_table_keeps_its_four_rows(self) -> None:
        workflow = self.read(WORKFLOW)
        self.assertIn("## 开工检查（写第一个文件之前）", workflow)
        for row in OPEN_CHECK_ROWS:
            self.assertIn(f"| {row} |", workflow, f"开工检查表缺少「{row}」行")

    def test_agents_requires_the_four_line_report(self) -> None:
        agents = self.read(AGENTS)
        self.assertIn("交付回复固定写四行", agents)
        for line in FOUR_LINES:
            self.assertIn(line, agents, f"四行证据缺少「{line}」")

    def test_human_gates_stay_the_same_four(self) -> None:
        agents = self.read(AGENTS)
        policy = self.read(POLICY)
        self.assertIn("人类门禁只有四类", agents)
        self.assertIn("人类门禁只保留四类", policy)
        for path, text in ((AGENTS, agents), (POLICY, policy)):
            for gate in HUMAN_GATES:
                self.assertIn(gate, text, f"{path.name} 缺少人类门禁「{gate}」")

    def test_invoked_skill_counts_as_data_egress_authorization(self) -> None:
        self.assertIn("用户当次点名的技能或命令", self.read(AGENTS))
        self.assertIn("调用本身构成数据外发授权", self.read(POLICY))
        self.assertIn("counts as authorization for its", self.read(MANAGED_BLOCK))

    def test_ambiguity_rule_survives_rule_edits(self) -> None:
        for path in (AGENTS, WORKFLOW):
            self.assertIn("两种合理解释", self.read(path),
                          f"{path.name} 丢了歧义处理规则")
        for path in (MANAGED_BLOCK, SKILL, OPENCODE_SKILL):
            self.assertIn("two reasonable readings", self.read(path).lower(),
                          f"{path} 丢了歧义处理规则")

    def test_consumer_managed_block_mirrors_the_entry(self) -> None:
        block = self.read(MANAGED_BLOCK)
        self.assertIn("Before the first write, confirm the 开工检查 gate", block)
        self.assertIn("Report in four lines", block)


if __name__ == "__main__":
    unittest.main()
