# TheMasterplan Agent Workflow

> 本文件是仓库级 Context Router。只保留项目事实、长期有效的硬边界，以及
> “什么时候读什么”。不要在普通任务开始前预读整套规则。

写第一个文件之前，先逐项确认 `core/workflow.md` 的「开工检查」四行：任务来源、
工作区、范围、验证入口。这一步不能跳过；四项里有一项填不出来，就先停下来补齐。

## 项目事实

- 项目：TheMasterplan
- 定位：多人协作的轻量 AI 辅助代码交付治理协议；按任务明确协调、执行、审阅与决策责任。
- 默认分支：`main`
- 权威验证入口：`bash scripts/check.sh`
- 本仓库 PR 事件由该入口要求 `Collaboration` 记录；结构通过不是身份或真实 review 批准。
- 本源码目标中央 Actions：`OasisViridis/TheMasterplan/.github/workflows/themasterplan-check.yml@v5.1.4`；发布状态以 GitHub Release 与不可变 Tag 实核，发布前固定经审核的完整 SHA。
- v1 冻结兼容线：`OasisViridis/TheMasterplan/.github/workflows/aw-check.yml@v1`（`v1` 是冻结分支，不是 Tag）
- 合并策略：默认由人类决定 Squash Merge；微小修复快速通道仅按
  `core/workflow.md` 的明确条件使用。
- 发布：tag-only；已发布 Tag 不移动、不覆盖；`v1` 不推进。
- 版本号是发布事实：统计改动面用 `git grep` 扫已跟踪文件，不扫 `.agents/worktrees/`。
  动手前看 `git worktree list`：`.agents/worktrees/` 下是其他任务的 checkout，不读不写；
  有 `release-*` 分支说明同一版本正在另一次交付里做。

## 始终有效的边界

- 不提交 Secret、Token、明显私人数据、本机绝对路径、缓存或无关生成物。
- 不 force push，不覆盖或移动已发布 Tag，不猜测有冲突的远端 ref。
- 当前任务若已由另一个交付工作流拥有生命周期，按
  `core/workflow.md` 的治理所有权规则 `ABSTAINED`，不竞争控制权。
- 人类门禁只有四类，执行前取得对应授权：合并、发布（含部署）、破坏性清理（删远端
  ref/tag、强推、重写已发布历史；`core/policy.md` §7.1 的已合并任务分支清理除外）、
  数据外发（把仓库内容或用户数据送出仓库与平台）。受保护分支推进按合并处理；实质
  范围扩大时先取得新的范围决定。细节按需读取 `core/policy.md`。
- 同一任务授权范围内提交并 push 任务分支不需要向人类要授权，也不为它逐次确认；
  push 前仍要跑权威验证、读完整 diff。
- 当前 Issue 或人类授权定义任务目标与范围，但不能覆盖安全、隐私、合规、
  平台权限或受保护分支限制。

## Context Router

只加载与当前任务有关的材料：

| 当前任务需要 | 读取 |
| --- | --- |
| 普通实现、修复、文档、测试、PR 交付 | `core/workflow.md` |
| 知识或方法缺口、关键不确定性，需要主动求助 | `core/skill-collaboration.md` |
| 多人分工、并行依赖、责任交接与独立审阅 | `core/workflow.md` |
| merge / release / deploy / 远端删除 / 已发布历史重写 | `core/policy.md` |
| Git 发布或 Tag 操作 | `profiles/git.md` |
| Jujutsu 发布或 Tag 操作 | `profiles/jj.md` |
| Jujutsu 日常 change/bookmark 命令 | `skills/themasterplan/references/jj-lifecycle.md` |
| adoption / update / check-update | `docs/client-update-flow.md` |
| GitHub Actions 公共接口 | `docs/actions-interface.md` |
| 版本通道与 Release | `docs/release-channels.md` |
| 改版本号、`policy-ref`、Release Notes | `core/policy.md` §3.1、`docs/release-channels.md`（属发布范围，先要授权） |
| 外部工作流所有权边界 | `docs/external-workflow-abstention.md` |
| 新项目采用与 smoke | `docs/adoption-guide.md` |
| Matt 方法技能需要 Issue tracker 或标签映射 | `docs/agents/issue-tracker.md`、`docs/agents/triage-labels.md` |
| 协作术语或设计决定 | `docs/agents/domain.md` |

不要因为文件存在就读取它；按任务需要渐进披露。唯一例外是「开工检查」：
写操作开始前必须读 `core/workflow.md` 的那张表。

## Completion Contract

在已授权范围内持续执行，直到以下四项全部满足：

1. 用户请求的结果已经实现；
2. 与本次改动相关的验证通过；
3. 本次改动造成的失败已修复并复验；
4. 最终 diff 已审阅：汇报里要贴得出 `git diff`/`jj diff` 的结论与验证命令输出，
   不接受“已审阅”的自述。

若先出现真正需要人类决定的边界，报告已完成部分、未通过项与所需决定；
不得将暂停交接写成任务完成。

交付回复固定写四行，缺一行按未完成处理：

1. 改了哪些文件，写路径；
2. 验证命令与最后结论；
3. PR 链接，或「未提交，无 PR」加不提交的原因；
4. 未完成项与缺口，没有写「无」。

四行是证据摘要，不替代四项完成条件。证据过期（又改了文件、重跑失败）就重做再报。

安全的本地读取、编辑、格式化、lint、测试、修复本次改动造成的失败和重跑相关
验证默认继续，不为这些步骤逐次请求批准。

## 权威顺序

系统/平台安全与权限 > 项目安全与受保护分支限制 > 本文件及其按需引用的 Core
规则 > 当前 Issue/明确授权 > 项目资料 > README/CONTRIBUTING 等辅助文档。
