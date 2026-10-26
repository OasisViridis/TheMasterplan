# jj Profile：发布事务确认与验证

> 本文件是 [Core Policy](../core/policy.md) 的 Jujutsu profile：jj 解析候选
> change，Git transport 创建 annotated tag 和推送，gh 创建 Release。
> 采用项目只需本 Profile 与已安装的 Core，不依赖另一个 Profile 或上游文档。
> Git transport 必须能访问当前 jj 仓库的 Git 元数据；不可用时停止并报告限制，
> 不为发布擅自初始化或转换仓库。

## 发布约束

- 候选 change 解析为完整 Git commit SHA，且等于最新 `origin/main`。
- 顺序：创建并 push tag → 固定 tag 消费者 smoke test → 创建 Release → 远端验证。
- `v1` 兼容线冻结：不推进稳定 bookmark，不执行 @v1 smoke，不要求 v1 与候选对齐。
- 授权、失效条件、部分失败恢复和最终审核要素以 `core/policy.md` 为准。
  人类批准精确完整事务后连续执行；不得逐步重复确认，也不得盲目重试。

## 阶段 A：自主准备

候选来自直接审核的既有 main SHA，或
[Core Policy §2.2](../core/policy.md#22-合并后受约束的派生发布候选) 核验通过的
唯一合并结果 SHA。派生路径先核验平台记录、main、已审预期树，重新完成完整
验证和消费者 smoke，再从审核记录注入固定 `APPROVED_CANDIDATE_SHA`；不得重跑
候选读取块用当前 `main` 或 change 顶替，相同树不允许使用任意 change。
执行身份与预期权限切换按 Core §1.2 核验。

只读检查、候选解析、验证和审核材料准备不需要逐步批准。

```bash
# 直接路径：解析审核时的 main 为完整 SHA。派生路径不执行本赋值，
# 改用下方“派生候选核验”块从审核记录注入固定结果 SHA。
jj git fetch --remote origin
APPROVED_CANDIDATE_SHA=$(git ls-remote origin refs/heads/main | awk '{print $1}')
[ -n "$APPROVED_CANDIDATE_SHA" ] || exit 1
jj --no-pager log -r "$APPROVED_CANDIDATE_SHA" --no-graph -T 'commit_id ++ "\n"'
git ls-remote --tags origin
jj tag list
```

### 派生路径：合并记录与结果核验

派生路径不执行上面的候选读取与赋值。按 Core §2.2 合并后，用下列只读命令
核验平台记录、结果树与父提交，再从审核记录注入固定结果 SHA；任何一项不一致、
注入缺失或当前 `main` 已移动即停止：

```bash
set -euo pipefail
APPROVED_PR_NUMBER="${APPROVED_PR_NUMBER:?set the approved PR number}"
APPROVED_HEAD_SHA="${APPROVED_HEAD_SHA:?set the review-time PR head SHA}"
APPROVED_BASE_SHA="${APPROVED_BASE_SHA:?set the review-time base SHA}"
APPROVED_RESULT_TREE="${APPROVED_RESULT_TREE:?set the reviewed expected result tree}"
APPROVED_MERGE_METHOD="${APPROVED_MERGE_METHOD:?set the approved merge method}"
APPROVED_CANDIDATE_SHA="${APPROVED_CANDIDATE_SHA:?set the fixed merged result SHA}"

jj git fetch --remote origin

# 1. 平台记录：PR 已合并到 main，head/base 与审核一致，mergeCommit 等于固定结果
[ "$(gh pr view "$APPROVED_PR_NUMBER" --json state --jq '.state')" = "MERGED" ] || exit 1
[ "$(gh pr view "$APPROVED_PR_NUMBER" --json headRefOid --jq '.headRefOid')" = "$APPROVED_HEAD_SHA" ] || exit 1
[ "$(gh pr view "$APPROVED_PR_NUMBER" --json baseRefOid --jq '.baseRefOid')" = "$APPROVED_BASE_SHA" ] || exit 1
[ "$(gh pr view "$APPROVED_PR_NUMBER" --json baseRefName --jq '.baseRefName')" = "main" ] || exit 1
[ "$(gh pr view "$APPROVED_PR_NUMBER" --json mergeCommit --jq '.mergeCommit.oid')" = "$APPROVED_CANDIDATE_SHA" ] || exit 1

# 2. 结果树与父提交：树等于审核预期树；Squash 唯一父提交等于审核 base
[ "$(git rev-parse "$APPROVED_CANDIDATE_SHA^{tree}")" = "$APPROVED_RESULT_TREE" ] || exit 1
[ "$APPROVED_MERGE_METHOD" = "squash" ] || exit 1
[ "$(git rev-parse "$APPROVED_CANDIDATE_SHA^")" = "$APPROVED_BASE_SHA" ] || exit 1

# 3. 当前远端 main 必须正好等于固定结果（否则按 Core §4 停止）
[ "$(git ls-remote origin refs/heads/main | awk '{print $1}')" = "$APPROVED_CANDIDATE_SHA" ] || exit 1
```

其他合并方式须在审核中另行列明可执行核验；未列明即不得走派生路径。

直接路径固定候选为 `APPROVED_CANDIDATE_SHA`；审核中不得用 `@`、`main` 或 change ID
前缀代替完整 SHA。§2.2 派生路径在合并前审核全部绑定项与唯一转换，合并后经
“派生候选核验”块固定结果并注入；不把 head 冒充结果、不重复批准获批范围。
审核完整列明 `core/policy.md` §2.1 与 §2.2 的要素：`TAG`、`NOTES_FILE`、
Notes 内容 SHA-256（最终文件字节，不规范化换行）、执行身份与预期受限凭据切换及
撤销核验、派生路径的 PR/head/base/预期树/合并方式与重验记录、完整写操作、顺序、
验证结果、当前远端状态、停止条件和已知风险。目标 tag 在本地和远端都必须不存在；
通过 gh 核实目标 Release 不存在。网络、认证或查询失败不是“不存在”的证据，
应停止核实。

## 阶段 C：执行已批准事务

仅在人类批准后执行。写入前重新核验 SHA、tag 与 Release 未变化；任何差异或
检查失败均按 Policy 停止重新审核。下列命令不是免除这些检查的快捷通道。

```bash
set -euo pipefail
APPROVED_CANDIDATE_SHA="${APPROVED_CANDIDATE_SHA:?set the approved full commit SHA}"
# 该变量只能来自审核记录；不得重新读取 main 或 change 顶替。
TAG="${TAG:?set the approved release tag}"
NOTES_FILE="${NOTES_FILE:?set the approved notes file}"
git check-ref-format "refs/tags/$TAG"
git fetch origin
CUR_MAIN=$(git ls-remote origin "refs/heads/main" | awk '{print $1}')
[ -n "$CUR_MAIN" ] && [ "$CUR_MAIN" = "$APPROVED_CANDIDATE_SHA" ] || exit 1
REMOTE_TAG=$(git ls-remote --tags origin "refs/tags/$TAG")
LOCAL_TAG=$(git tag --list "$TAG")
[ -z "$REMOTE_TAG" ] && [ -z "$LOCAL_TAG" ] || exit 1
# 成功查询全部 Release 后才可判定不存在；认证、网络、分页失败均退出。
REPOSITORY=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
[ -n "$REPOSITORY" ] || exit 1
RELEASE_TAGS=$(gh api "repos/$REPOSITORY/releases" --paginate --jq '.[].tag_name')
if printf '%s\n' "$RELEASE_TAGS" | grep -Fxq -- "$TAG"; then
  echo "release already exists: $TAG" >&2
  exit 1
fi
git tag -a "$TAG" -m "Release $TAG" "$APPROVED_CANDIDATE_SHA"
git push origin "$TAG"
```

现在运行审核中列明的**固定 tag 消费者 smoke test**并检查退出码与结果。
没有实际成功证据（仅有注释、计划或构造命令不算通过）时，不得运行以下命令：

```bash
gh release create "$TAG" --verify-tag --title "$TAG" --notes-file "$NOTES_FILE"
```

不使用 `jj tag set` 替代上述 annotated tag 创建：它会移动已有 tag，也不满足
本发布路径的 annotated tag 契约。已批准操作部分成功时先核验远端状态，不猜测、
不自动删除残留 tag、不用强推恢复。

## 阶段 D：发布后验证

```bash
set -euo pipefail
jj git fetch --remote origin
TAG_COMMIT=$(git ls-remote --tags origin "refs/tags/$TAG^{}" | awk '{print $1}')
[ "$TAG_COMMIT" = "$APPROVED_CANDIDATE_SHA" ] || exit 1
gh release view "$TAG" --json tagName,isDraft,isPrerelease
jj --no-pager log -r "$APPROVED_CANDIDATE_SHA" --no-graph -T 'commit_id'
```

核对 peeled SHA 等于候选、`tagName == TAG`、`isDraft == false`、Notes 正确，
无审核范围外 ref 或修改；`v1` 保持冻结。任何差异停止并重新审核。

## 禁止

- 用含糊 revision 或非最新 `origin/main` 的候选发布。
- 未批准就创建 tag、push 或创建 Release，或 smoke 未通过就创建 Release。
- 强推、覆盖/移动/删除已发布 tag、擅自推进稳定 bookmark。
- 跳过远端验证，或把查询失败、计划、注释当作成功证据。
- 违反 Core Policy 的授权失效与部分失败边界。
