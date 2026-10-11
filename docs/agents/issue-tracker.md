# Issue tracker：GitHub

本仓库使用 GitHub Issues。操作前从实际 `git remote -v` 与 `gh repo view`
核对仓库身份，不缓存账号名或把历史链接当作当前写入目标。

- 创建：`gh issue create --title "..." --body-file <file>`；多行正文写 UTF-8 文件。
- 读取：`gh issue view <number> --comments`；筛选时读取 labels 和 assignees。
- 列表：`gh issue list --state open --json number,title,body,labels,assignees`。
- 留言：`gh issue comment <number> --body-file <file>`。
- 标签：`gh issue edit <number> --add-label <state> --remove-label <old-state>`。
- 自行认领：`gh issue edit <number> --add-assignee @me`，随后重新读取实际归属；
  条件和重复认领处理以 [Core Workflow](../../core/workflow.md) §1.2 为准。
- 完成：核验全部验收条件后 `gh issue close <number>`；关闭本身不证明依赖满足。

父子 Issue 使用原生 sub-issues，阻塞使用原生 `Blocked by / Blocking`。
按当前 CLI `--help` 或 GitHub REST 文档选择可用命令；依赖 endpoint 的
`issue_id` 是数据库 ID，不是 Issue 编号。下游正文说明具体所需结果，并按
Core §1.3 核验已合并和验收证据；不能只以 open blocker 数量为零筛选。

当 skill 要求 “publish to the issue tracker”，创建 GitHub Issue；当要求
“fetch the relevant ticket”，读取对应 Issue 与评论。准备标签映射见
[triage-labels.md](triage-labels.md)。

**PRs as a request surface: no.** PR 是交付与批准入口，外部 PR 不自动进入 triage。

Issue/PR 创建、指派与评论不授予 merge/release/deploy 权限，仍以 Core 和当前
人类授权为准。Matt 方法技能补足交付步骤，TheMasterplan 保持治理所有权。
