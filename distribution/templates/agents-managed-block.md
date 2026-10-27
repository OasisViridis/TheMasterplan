<!-- THEMASTERPLAN:BEGIN MANAGED -->
# TheMasterplan

This block is the project Context Router. Load guidance only when the task needs it.

- routine delivery and external-ownership decisions: `core/workflow.md`
- knowledge or method gaps / critical uncertainty: `core/skill-collaboration.md`
- team roles, parallel dependencies, handoff and independent review: `core/workflow.md`
- authorization / merge / release / destructive remote action: `core/policy.md`
- VCS release/tag: load the selected installed profile under `profiles/`
  (the adopted project contains only its selected profile)
- adoption/update maintenance: use the installed `.themasterplan/bin/themasterplan.py`
  commands; consult upstream adoption/update docs only for that maintenance task

Do not preload the whole rule stack.

Before the first write, confirm the 开工检查 gate in `core/workflow.md`: task source,
workspace, scope, validation entry. A row you cannot fill stops the edit.
Before reporting done, run the repository validation entry and include its output.

When a protocol term, gate category, or acceptance bar has two reasonable readings,
list both and ask the human; do not invent a definition or widen or narrow a human
gate. Asking about ambiguity is not an approval request.

Safe local reading, editing and validation continue without per-step approval;
unknown checks require side-effect inspection, not an assumption of safety.

Pushing a task branch is not an approval gate: do not ask for push permission per
change. Human gates are merge, release, destructive cleanup, and sending repo or
user data outside the repository and platform. A skill or command the person
actively ran for that call counts as authorization for the destination its
documentation names: send the requested content, do not ask again and
do not redact it to avoid the gate. A mere mention of the command is not
authorization, and neither is a call the agent starts on its own; content scope
follows that call, and recipient checks, credentials and safety limits follow
`core/policy.md` §1 and §1.2.

## Completion Contract

Within the authorized scope, continue until the requested result exists, relevant
validation passes, failures caused by the change are fixed and revalidated, and
the final diff is reviewed. All four conditions are required. At a genuine human
decision boundary, report unfinished work and the needed decision, not completion.

Report in four lines: files changed, validation command and result, PR link or
"not submitted, no PR" with the reason, remaining gaps. The four lines summarize
evidence; they do not replace a real validation run on the final candidate.
<!-- THEMASTERPLAN:END MANAGED -->

## 项目事实

<!-- 在此维护项目名、目标、默认分支、验证入口、受保护分支和项目特定约束。
     TheMasterplan apply/update 只管理上方区块。 -->
