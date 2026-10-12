# 全流程审阅与修改计划

> 下文是 2026-10-12 的定稿审阅快照，“本轮”指该次审阅，不代表后续实施状态。
> 实施状态另见[全流程实施任务](https://github.com/OasisViridis/TheMasterplan/issues/110)；
> 本次 C 候选落实 F6/F7，A/B/D/E 按各自任务与依赖交付，合入和发布另行决定。

审阅日期：2026-10-12。基线：`e43927615d7901ccb7531f5b3c311a56143c7338`，
内容树：`6279319973eb759c5f1854e60a609d9f5db745fa`。
只读 GitHub 查询确认当前 `main` 与该基线一致；[PR #109](https://github.com/OasisViridis/TheMasterplan/pull/109)
已合并，[v5.1.2 Release](https://github.com/OasisViridis/TheMasterplan/releases/tag/v5.1.2)
已发布且不是 Draft 或 Prerelease。当前提交见[基线](https://github.com/OasisViridis/TheMasterplan/commit/e43927615d7901ccb7531f5b3c311a56143c7338)。

状态：审阅已完成，修改计划已于 2026-10-12 经人类在当前会话以“定稿”确认。
设计定稿不表示 Core 已修改，也不授权实施、创建 Issue/PR、push、合并或发布。

## 已确认的设计方向

- 先补齐正确性，再减少流程负担；保持两三位人类各自使用 Agent 的协作模式。
- 日常凭据保持低权限；批准后的合并/发布使用单独授予的受限执行凭据。
  授权和实际平台权限分别核验，不赋予 admin 或绕过保护规则的能力。
- 一次“合并并发布”授权可以覆盖明确受约束的派生发布候选。
  绑定 PR head、审核基线和内容树；合并后重新验证，内容或范围变化重新审核。
- 在现有脚本和测试补齐采用计划完整性、失败停止和发布证据核验。
  认领争议、批准资格和真实 review 仍通过平台证据与有权人类决定核验。

对应设计依据见 [ADR 0002](adr/0002-scoped-execution-permissions.md)
和 [ADR 0003](adr/0003-derived-release-candidates.md)。两者已随计划定稿接受，尚待实施。

## 全流程覆盖与证据边界

| 阶段 | 当前机制 | 审阅结论 |
| --- | --- | --- |
| 治理接入与外部所有权 | Context Router、任务级 ABSTAINED、平台 CI 独立运行 | 边界明确；不把普通工具或团队分工当作外部接管 |
| 采用、来源固定、落地 | inspect、plan-adopt、apply-adopt、state | 确认 F1/F2；采用执行保护弱于更新保护 |
| 版本检测与更新 | 意图触发、固定来源、逐文件 hash、规范计划复核 | 已有完整执行器计划与保护机制，应作为采用修复的参照 |
| 任务准备与认领 | Issue 范围、状态标签、唯一 Assignee、重新读取 | 非原子认领的限制与争议恢复已写明；补可复制记录即可 |
| 并行与依赖 | 独立工作区/ref/PR、共享逻辑唯一负责人、上游合入并验收 | 规则明确；不新增调度器或以 Issue closed 代替验收 |
| 实现、验证、自审 | 按风险验证、push 前完整检查与最终 diff | 本地权威检查通过；CI 策略来源存在 F3 |
| 技术审阅、批准与合并 | 独立技术审阅绑定 SHA、人类批准单独核验、平台保护 | 原则保留；F6/F7 的权限与候选转换规则需统一 |
| 整体验收、释放与交接 | 父任务验收、停止旧作业、保存交接、再认领 | 规则已有；建议降低记录和核验成本，不把模板当成作业已停止的证明 |
| Tag、smoke、Release、恢复 | 不可变 annotated Tag、tag-only、固定 Tag smoke、部分失败核验 | 确认 F4/F5；需要验证实际执行路径 |
| 清理与反馈 | 已合并自建任务 ref 的有限清理豁免、消费者前向修复 | 保留精确删除与不可变历史边界；修订 F8 的过时状态叙述 |

上述覆盖生命周期和主要执行入口，不等于已完成真实多人演练、GitHub Ruleset
验收或所有宿主验证。静态记录校验不证明身份、权限、独立性或真实批准，这属于
已明确的边界，不作为新增缺陷。

## 确认的问题

### F1：采用计划未展示完整执行器写入，已有修改会被覆盖

优先级：高，实施前优先修复。

[`planning.py`](../skills/themasterplan/scripts/tmlib/planning.py) 从 manifest 与生成
模板构造计划；manifest 仅显式包含一个执行器文件 `update_check.py`。
[`apply.py`](../skills/themasterplan/scripts/tmlib/apply.py) 的 `executor_entries` /
`install_executor` 另行安装完整的 12 文件 bundle，剩余 11 个没有出现在采用计划。
安装逻辑在内容不同的情况下直接写入，没有对应的既有执行器冲突分类。

隔离复现：项目预先存在本地修补的 `.themasterplan/bin/tmlib/apply.py`，生成计划
没有该目标且没有 stop condition，应用后该修补被覆盖。
这与[更新文档](client-update-flow.md)“不得以 apply-adopt 绕过执行器修改保护”冲突。

修改：把完整 bundle 纳入采用计划，逐文件显示来源、所有权、当前/目标 hash 与
分类；已有不同内容或未登记的安装停止。apply 只执行计划内操作。
已有 CURRENT/MODIFIED/BROKEN 安装的维护走更新/诊断路径，不能把 adopt 当恢复捷径。

### F2：采用应用没有核验完整操作集合来自规范计划

优先级：高，与 F1 同批修复。

[`apply_adopt`](../skills/themasterplan/scripts/tmlib/apply.py) 核验 schema、路径、
来源身份和必需 profile 映射，却没有像 `apply_update` 一样重建并比较完整计划。
隔离复现：保留必需映射，追加一个来源为 `core/policy.md` 的合法相对目标，
应用会写出该额外文件。

修改：应用前对照固定来源、选择项、manifest 和项目当前状态重新核验全部操作。
拒绝增删目标、变更所有权、伪造分类/来源及源或目标漂移。人类审核记录绑定计划
摘要；规范计划复核证明操作合法，摘要与授权记录证明使用的是已审核计划，两者
不能相互代替。保留“同一计划已完整落地且内容一致”的幂等重试，不采用会误拒绝
已成功应用的简单字典全等比较。

### F3：仓库改名后自身 CI 会选择历史策略

优先级：高，可与采用修复并行。

GitHub [当前仓库 API](https://api.github.com/repos/OasisViridis/TheMasterplan) 的身份为
`OasisViridis/TheMasterplan`；[旧名 API](https://api.github.com/repos/OasisSaber/TheMasterplan)
查询也返回当前身份。查询只核验托管身份，不自动改变历史包或 state 的来源标识。
[`themasterplan-check.yml`](../.github/workflows/themasterplan-check.yml) 的自身判断
仍硬编码 `OasisSaber/TheMasterplan`。因此当前仓库被走入消费者分支，检出默认
`policy-ref: v1`，与[Actions 接口](actions-interface.md)“自身 PR 使用当前候选策略”
不一致。这个结论来自已核验身份与条件分支，不声称本轮运行了远端 CI。

修改：修正自身策略选择并加入当前身份、已知历史身份和外部消费者三类回归。
清点 manifest、来源校验、链接与示例中的仓库身份，明确历史来源兼容方案；
不能全局替换后让历史 state/不可变包的来源验证失效，不能修改已发布 Tag。
不新增中央 Actions 输入，也不改变 required check 公共接口。

### F4：Git 发布检查把查询错误当成资源不存在

优先级：高。

[`profiles/git.md`](../profiles/git.md) 用 `if gh release view ...` 判定存在；网络、
认证等非零退出会落到“不存在”路径。`if git ls-remote ... | grep -q .` 同样把
查询失败与空结果混合；本地 tag 检查还有 `|| true`。
jj Profile 已采用成功查询后判断列表的方式，两条路径不一致。

隔离替身复现：执行 Git Profile 的原始阶段 C 命令块，让 Release 查询退出 2，
命令仍依次执行了替身 tag/create、push、release/create，并返回成功。

修改：查询成功与结果判定分开；任何网络、认证、分页或本地元数据错误停止。
对齐 Git/jj 的检查、目标 ref 校验与发布后断言。

### F5：Git 发布命令块没有可执行 smoke 门，测试验证另一套逻辑

优先级：高，与 F4 同批修复。

Git Profile 在 push 与 Release 之间只有 smoke 注释，复制整个命令块执行会直接
创建 Release。jj Profile 已拆开命令块并明确要求实际成功证据。
[`test_release_flow.py`](../scripts/test_release_flow.py) 自行重写事务，用布尔值
表示 smoke 是否通过，gh 只构造命令；它没有执行 Profile 命令块，覆盖不了 F4/F5。

修改：Git/jj 使用同一套可核验发布门；smoke 的候选、命令、退出码及证据在审核中
列明，未执行、失败或身份不符时不能进入 Release。Notes 内容摘要与目标候选也需
绑定，并在外部写入前复核。测试运行实际使用的入口或提取文档原始命令，避免复制
第二套事务逻辑。新增工具只能用于已批准事务，不引入自动授权或自动发布。

### F6：凭据规则与批准后执行责任冲突

优先级：中，涉及已确认设计选择。

[仓库设置](repository-settings.md) 禁止 Agent 凭据拥有 merge/release 权限；
[Core Policy](../core/policy.md) 要求 Agent 执行已批准操作，不交给人类手工执行。
两条规则缺少日常与获批执行阶段的区分；Policy 又把工具权限变化列为授权失效条件。

修改：按 ADR 0002 区分日常与获批执行能力。审核列明预期凭据切换、动作和目标；
该预期切换不触发重复批准，实际平台权限不足或出现审核外权限变化则停止。
选择最小可用平台权限，不共享身份、提交凭据或授予 admin，不自动放宽 Ruleset。

### F7：精确 SHA 失效规则未表达合并后发布的受约束转换

优先级：中，涉及已确认设计选择。

默认 Squash Merge 产生新 commit；[Core Policy §4](../core/policy.md#4-聚合授权失效条件)
规定候选 SHA 变化即失效，而两个发布 Profile 都要求候选等于最新 `origin/main`。
当前文字无法完整表达一次批准“合并并发布”后的候选转换。

修改：按 ADR 0003 增加显式授权路径。最终审核记录 PR、head SHA、base SHA、
预期结果内容树、目标 Tag、Notes 摘要和允许转换；合并前核验 head/base/保护门，
合并后核验平台合并记录、main SHA 和预期内容树，再运行完整验证与消费者 smoke。
远端移动、结果树变化、额外提交、验证失败或身份不符均停止。不得把“树相同”
推广为任意 SHA、任意 main 或任意事务可复用旧授权。保留直接批准既有 main SHA
的 tag-only 发布路径。

### F8：辅助资料保留了过时的当前状态叙述

优先级：低，随对应功能修复同步。

[协作设计](team-collaboration-design.md) 仍称“尚待 PR 审阅与人类合并”，但平台
确认 PR #109 已合并。[仓库设置](repository-settings.md) 仍称 check.yml 仅有
reusable job，实际还有 Windows regressions；[CONTRIBUTING](../CONTRIBUTING.md)
也需要区分 Windows 回归 job 与完整 Windows 采用验收。

修改：给历史迁移与当前文件事实分别标日期/来源；实际 Ruleset、真实团队演练和
完整平台采用验收保留未核验边界，不把新增 Windows job 写成完整支持已通过。

## 实施顺序与任务边界

| 批次 | 范围与主要文件 | 前置条件 | 验收与结束条件 |
| --- | --- | --- | --- |
| A：采用保护 | F1/F2；planning.py、apply.py、采用/安全测试、更新文档；读取既有 manifest，不改来源身份 | 最终计划确认 | 全 bundle 出现在计划；本地修改/删改计划/源与目标漂移均拒绝且零写入；首次采用、幂等重试、Git/jj 来源验证通过 |
| B：CI 来源与身份 | F3；中央 workflow、Actions 契约测试、source.py/manifest 的必要兼容、身份相关文档 | 最终计划确认；历史身份兼容方案先形成可测试规格 | 当前自身 PR 用当前策略；历史别名兼容；外部消费者仍用显式固定版本；required check 名称/只读权限不变 |
| C：授权一致性 | F6/F7；policy.md、repository-settings.md、Git/jj Profiles、ADR | 设计方向已确认；最终计划确认 | 日常/获批凭据职责一致；受约束派生与普通 SHA 失效路径有正反例；原生保护门不能绕过 |
| D：发布执行门 | F4/F5；Git/jj Profiles、实际发布检查入口或文档提取测试、test_release_flow.py | C 的候选与权限模型固定 | 查询错误零外部写入；smoke 缺失/失败不创建 Release；Notes/候选漂移停止；真实临时 Git 事务与 gh 替身故障注入测试覆盖实际入口 |
| E：记录与演练 | F8、交接示例与批准记录说明；协作设计、采用文档、模板说明、CONTRIBUTING | 对应批次实现完成 | 历史/当前/未核验边界清楚；认领争议、释放、协调权移交、依赖失效和整体验收场景有输入、预期、实际证据位置 |

A/B 可分别交付；`distribution/manifest.json` 与 `source.py` 的身份兼容修改唯一
归 B 负责人，A 在 planning/apply 使用既有 bundle 定义，不修改这两个共享入口。
若实施发现 A 必须改变 manifest/schema，则先调整任务边界，由 B 交付该共享结果，
A 建立阻塞依赖；不能继续按原并行假设修改。B 合入后复验 A 的来源与采用回归。
C/D 按顺序交付。每个实施单元一位负责人、独立工作区和 PR。
每批完整权威检查、最终 diff 与未参与实现的 Agent 技术审阅
通过后，提交人类批准。实施 Issue 的创建、认领与 PR 操作按后续明确授权执行。

E 不收紧历史消费者默认契约：`Human approval` 的历史可选策略保留；若采用项目
要对新格式强制记录，另列模板/开放 PR 迁移与显式严格模式，不靠绿色 CI 宣称批准。
提供一个可复制的交接记录，引用 Core 要求，不维护另一套平行规则。

## 本轮验证与后续验收

- 已执行 `bash scripts/check.sh`：241 项测试，7 项跳过，其余通过；Markdown
  链接、Shell mode、YAML 和 Shell syntax 全通过。本地非 PR 事件没有核验真实批准。
- F1/F2 在临时目录调用当前真实执行器复现；F4/F5 提取当前 Git Profile 原始阶段 C
  命令块，用本地 git/gh 替身复现，没有远端写入。
- GitHub 仅只读核验仓库身份、main、PR #109 与 Release 状态；没有核验所有 Ruleset、
  权限、远端 CI 来源或真实多人行为。
- 实施后每批运行权威检查；针对行为改动增加上述正反例。
  发布前做固定 SHA 消费者 Git/jj smoke；批准后建 Tag，再做固定 Tag smoke，最后
  创建 Release 与核验 peeled SHA/Notes。发布性操作必须有对应授权。
- 不移动历史 Tag、冻结 v1 或未经授权更新任何采用项目；新版本号和实际发布属于
  后续独立决定。本轮没有修复这些行为问题，也没有发布新版本。

## 定稿记录

2026-10-12，人类在当前会话明确回复“定稿”，确认本计划的目标、边界、顺序与
验收，以及 ADR 0002/0003 的设计决定。访谈已达成共同理解，计划定稿。
本次决定只确认设计；实施与外部交付仍按后续明确授权范围进行。
