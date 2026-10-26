"""Apply TheMasterplan adoption plans with immutable source locking."""

from __future__ import annotations

import json
from pathlib import Path

from .source import Source, read_package_file
from .util import (
    TheMasterplanError,
    read_json,
    safe_join,
    sha256_of_block,
    sha256_of_file,
    validate_relative_path,
    validate_target_paths,
    validate_state,
    apply_file_changes,
    sha256_of_block_bytes,
)

BLOCK_BEGIN = "<!-- THEMASTERPLAN:BEGIN MANAGED -->"
BLOCK_END = "<!-- THEMASTERPLAN:END MANAGED -->"
BLOCK_BEGIN_BYTES = BLOCK_BEGIN.encode("utf-8")
BLOCK_END_BYTES = BLOCK_END.encode("utf-8")
SELF_PREFIX = "<self>:"

EXECUTOR_FILES = (
    "themasterplan.py",
    "tmlib/__init__.py",
    "tmlib/util.py",
    "tmlib/manifest.py",
    "tmlib/source.py",
    "tmlib/inspect.py",
    "tmlib/planning.py",
    "tmlib/apply.py",
    "tmlib/verify.py",
    "tmlib/update.py",
    "tmlib/doctor.py",
    "tmlib/update_check.py",
)


class ApplyError(TheMasterplanError):
    """Raised when a plan cannot be applied safely."""


def _sha256_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _validate_plan(plan: dict) -> None:
    if not isinstance(plan, dict):
        raise ApplyError("plan must be an object")
    if plan.get("schema_version") != 1 or plan.get("plan_type") != "adopt":
        raise ApplyError("unsupported plan: schema_version/plan_type mismatch")
    if not isinstance(plan.get("selection"), dict) or plan["selection"].get("profile") not in ("git", "jj"):
        raise ApplyError("plan selection requires git or jj profile")
    if set(plan["selection"]) != {"profile", "validation_path", "default_branch"}:
        raise ApplyError("plan selection fields differ; regenerate and review")
    for key in ("validation_path", "default_branch"):
        value = plan["selection"].get(key)
        if not isinstance(value, str) or not value:
            raise ApplyError(f"plan selection missing {key}")
        validate_relative_path(value)
    for key in ("source", "selection", "files"):
        if key not in plan:
            raise ApplyError(f"plan missing key: {key}")
    if plan.get("stop_conditions"):
        raise ApplyError(f"plan has stop conditions: {plan['stop_conditions']}")
    files = plan["files"]
    if not isinstance(files, list) or not files:
        raise ApplyError("plan files must be a non-empty list")

    seen: set[str] = set()
    for operation in files:
        if not isinstance(operation, dict):
            raise ApplyError("plan file entry must be an object")
        for key in ("source", "destination", "ownership", "classification"):
            if key not in operation:
                raise ApplyError(f"plan file entry missing key: {key}")
        source = operation["source"]
        if not isinstance(source, str) or not source:
            raise ApplyError("plan source must be a non-empty string")
        destination = operation["destination"]
        if not isinstance(destination, str) or not destination:
            raise ApplyError("plan destination must be a non-empty string")
        validate_relative_path(source)
        validate_relative_path(destination)
        if destination in seen:
            raise ApplyError(f"plan has duplicate destination: {destination}")
        seen.add(destination)
        if operation["ownership"] not in (
            "managed-replace",
            "managed-block",
            "generated-if-missing",
            "project-owned",
        ):
            raise ApplyError(
                f"unknown ownership: {operation['ownership']}"
            )
        if operation["classification"] not in (
            "ADD",
            "UNCHANGED",
            "CONFLICT",
            "BLOCK_PRESENT",
            "BLOCK_MISSING",
            "EXISTS_KEEP",
            "PROJECT_OWNED",
        ):
            raise ApplyError(
                f"unknown classification: {operation['classification']}"
            )
    validate_target_paths([op["destination"] for op in files] + [".themasterplan/state.json"])


def _read_self(relative: str) -> bytes:
    executor_root = Path(__file__).resolve().parent.parent
    return read_package_file(executor_root, relative)


def _read_package_bytes(package_root: Path | None, operation: dict) -> bytes:
    source = operation["source"]
    if source.startswith(SELF_PREFIX):
        content = _read_self(source[len(SELF_PREFIX) :])
    else:
        if package_root is None:
            raise ApplyError(
                f"plan requires package source for "
                f"{operation['destination']}; pass --source"
            )
        content = read_package_file(package_root, source)
    expected = operation.get("source_sha256")
    if expected and _sha256_bytes(content) != expected:
        raise ApplyError(f"source file changed since plan: {source}")
    return content


def _block_bounds_bytes(data: bytes) -> tuple[int, int] | None:
    if data.count(BLOCK_BEGIN_BYTES) != 1 or data.count(BLOCK_END_BYTES) != 1:
        return None
    begin = data.find(BLOCK_BEGIN_BYTES)
    end = data.find(BLOCK_END_BYTES)
    if end < begin:
        return None
    return begin, end + len(BLOCK_END_BYTES)


def _block_bounds(text: str) -> tuple[int, int] | None:
    if text.count(BLOCK_BEGIN) != 1 or text.count(BLOCK_END) != 1:
        return None
    begin = text.index(BLOCK_BEGIN)
    end = text.index(BLOCK_END)
    if end <= begin:
        return None
    return begin, end + len(BLOCK_END)


def _block_content_matches(destination: Path, block_content: bytes) -> bool:
    data = destination.read_bytes()
    bounds = _block_bounds_bytes(data)
    if bounds is None:
        return False
    begin, end = bounds
    content_end = block_content.find(BLOCK_END_BYTES)
    if content_end < 0:
        return False
    expected = block_content[: content_end + len(BLOCK_END_BYTES)]
    return data[begin:end].strip() == expected.strip()


def _current_hash(target: Path, ownership: str) -> str:
    if ownership == "managed-block":
        return sha256_of_block(target)
    return sha256_of_file(target)


def _check_observed(project_root: Path, operation: dict) -> None:
    destination = safe_join(project_root, operation["destination"])
    observed = operation.get("observed_sha256")
    if observed is None:
        raise ApplyError(
            f"plan missing observed hash: {operation['destination']}"
        )
    if (
        not destination.is_file()
        or _current_hash(destination, operation["ownership"]) != observed
    ):
        raise ApplyError(
            f"target changed since plan: {operation['destination']}"
        )


def _render_template(content: bytes, plan: dict) -> bytes:
    text = content.decode("utf-8")
    selection = plan.get("selection", {})
    text = text.replace(
        "{{validation_path}}",
        selection.get("validation_path", "scripts/check.sh"),
    )
    text = text.replace(
        "{{default_branch}}",
        selection.get("default_branch", "main"),
    )
    return text.encode("utf-8")


def _make_minimal_agents(block_content: bytes) -> bytes:
    block = block_content.decode("utf-8")
    return (
        "# TheMasterplan\n\n"
        "> 本文件由 /TheMasterplan 接入生成；规则由 TheMasterplan 管理区块声明。\n\n"
        f"{block}\n"
    ).encode("utf-8")


def _prepare_sources(
    plan: dict,
    package_root: Path | None,
) -> dict[str, bytes]:
    prepared: dict[str, bytes] = {}
    for operation in plan["files"]:
        if operation["classification"] not in (
            "ADD",
            "UPDATE_SAFE",
            "BLOCK_PRESENT",
        ):
            continue
        prepared[operation["destination"]] = _read_package_bytes(
            package_root,
            operation,
        )
    return prepared


def _executor_root(source: Source | None) -> Path:
    if source is None:
        return Path(__file__).resolve().parent.parent

    candidates = (
        source.package_root / "skills" / "themasterplan" / "scripts",
        # Temporary compatibility for a branch before the directory rename.
        source.package_root
        / "skills"
        / "agentic-wonderwall"
        / "scripts",
    )
    for candidate in candidates:
        if (candidate / "themasterplan.py").is_file():
            return candidate
    raise ApplyError(
        "source package does not contain the TheMasterplan executor"
    )


def executor_entries(source: Source) -> list[dict]:
    """Expand the exact target bundle into auditable package-source operations."""
    root = _executor_root(source)
    prefix = root.relative_to(source.package_root.resolve()).as_posix()
    return [{"source": f"{prefix}/{relative}",
             "destination": f".themasterplan/bin/{relative}",
             "ownership": "managed-replace", "required": True}
            for relative in EXECUTOR_FILES]


def _check_precondition(
    project_root: Path,
    operation: dict,
    prepared_sources: dict[str, bytes],
    plan: dict,
) -> None:
    destination = safe_join(project_root, operation["destination"])
    classification = operation["classification"]
    if classification == "ADD":
        if destination.exists():
            content = prepared_sources[operation["destination"]]
            if operation["ownership"] == "managed-block":
                if _block_content_matches(destination, content):
                    return
                raise ApplyError(
                    "managed block differs: "
                    f"{operation['destination']}"
                )
            rendered = (
                _render_template(content, plan)
                if operation.get("render")
                else content
            )
            if destination.is_file() and (
                sha256_of_file(destination) == _sha256_bytes(rendered)
            ):
                return
            raise ApplyError(
                f"plan says ADD but target exists: "
                f"{operation['destination']}"
            )
        return
    if classification == "UNCHANGED":
        if not destination.is_file():
            raise ApplyError(
                f"plan says UNCHANGED but file is missing: "
                f"{operation['destination']}"
            )
        _check_observed(project_root, operation)
        return
    if classification in ("EXISTS_KEEP", "PROJECT_OWNED"):
        _check_observed(project_root, operation)
        return
    if classification == "CONFLICT":
        raise ApplyError(
            f"managed file conflict: {operation['destination']}"
        )
    if classification == "BLOCK_MISSING":
        raise ApplyError(
            f"managed block missing: {operation['destination']}"
        )
    if classification == "BLOCK_PRESENT":
        if not destination.is_file():
            raise ApplyError(
                f"managed-block target missing: "
                f"{operation['destination']}"
            )
        if _block_bounds(destination.read_text(
            encoding="utf-8",
            errors="replace",
        )) is None:
            raise ApplyError(
                f"managed block markers invalid: "
                f"{operation['destination']}"
            )
        _check_observed(project_root, operation)
        return
    raise ApplyError(f"unknown classification: {classification}")


def _build_state(plan: dict, contents: dict[str, bytes | None]) -> dict:
    managed = {}
    for operation in plan["files"]:
        ownership = operation["ownership"]
        if ownership not in ("managed-replace", "managed-block"):
            continue
        relative = operation["destination"]
        data = contents[relative]
        if data is None:
            raise ApplyError(f"managed target missing: {relative}")
        managed[relative] = {
            "source": operation["source"],
            "source_sha256": operation["source_sha256"],
            "installed_sha256": (sha256_of_block_bytes(data) if ownership == "managed-block"
                                 else _sha256_bytes(data)),
            "ownership": ownership,
        }
    return {
        "schema_version": 1,
        "source": plan["source"],
        "selection": plan["selection"],
        "managed_files": managed,
        "adoption_plan_sha256": plan["plan_sha256"],
        "adoption": {"date": None, "platform": None, "git_version": None,
                     "jj_version": None, "status": "PARTIAL"},
    }


def apply_adopt(project_root: Path, plan_path: Path, source: Source | None = None,
                *, reviewed_plan_sha256: str | None = None) -> dict:
    from .planning import adopt_plan_digest, plan_adopt

    plan = read_json(plan_path)
    _validate_plan(plan)
    digest = adopt_plan_digest(plan)
    if plan.get("plan_sha256") != digest:
        raise ApplyError("plan summary mismatch; regenerate and review")
    if reviewed_plan_sha256 is not None and digest != reviewed_plan_sha256:
        raise ApplyError("plan does not match the reviewed summary")
    if source is None:
        raise ApplyError("apply-adopt requires --source")
    if source.as_dict() != plan.get("source"):
        raise ApplyError("resolver source does not match plan source")
    if sha256_of_file(source.package_root / "distribution/manifest.json") != plan.get("manifest_sha256"):
        raise ApplyError("manifest changed since plan; regenerate and review")

    # Read all sources, including kept files, before any target write.
    prepared = {op["destination"]: _read_package_bytes(source.package_root, op)
                for op in plan["files"] if op["ownership"] != "project-owned"}
    state_path = safe_join(project_root, ".themasterplan/state.json")
    expected = {}
    for op in plan["files"]:
        target = safe_join(project_root, op["destination"])
        if target.exists() and not target.is_file():
            raise ApplyError(f"target is not a regular file: {op['destination']}")
        expected[op["destination"]] = target.read_bytes() if target.is_file() else None
    expected[".themasterplan/state.json"] = state_path.read_bytes() if state_path.is_file() else None

    if state_path.exists():
        state = validate_state(read_json(state_path))
        if (state.get("adoption_plan_sha256") != digest or state["source"] != plan["source"]
                or state["selection"] != plan["selection"]):
            raise ApplyError("existing installation: use plan-update or doctor, not adoption")
        # A receipt alone is not enough: only the full, unchanged managed result
        # can retry. Project-owned and generated-if-missing files stay owned by
        # the project, so edits there do not invalidate a completed adoption.
        # A missing required generated file (e.g. the validation entrypoint) is
        # still drift and must not be reported as a successful retry.
        for op in plan["files"]:
            relative = op["destination"]
            data = expected[relative]
            ownership = op["ownership"]
            if ownership in ("project-owned", "generated-if-missing"):
                if ownership == "generated-if-missing" and op.get("required") and data is None:
                    raise ApplyError(f"required generated target missing: {relative}")
                continue
            current = (sha256_of_block_bytes(data) if ownership == "managed-block"
                       else _sha256_bytes(data)) if data is not None else None
            if current != op.get("target_sha256"):
                raise ApplyError(f"completed adoption target changed: {op['destination']}")
        result_state = _build_state(plan, expected)
        if state["managed_files"] != result_state["managed_files"]:
            raise ApplyError("completed adoption state changed; use doctor")
        # Recheck snapshots without writes before returning the idempotent result.
        apply_file_changes(project_root, {}, expected)
        return {"written": [], "unchanged": [op["destination"] for op in plan["files"]]}

    # Normal application must match the entire current canonical plan. This also
    # rejects partial retries, hidden writes, changed selection and forged fields.
    canonical = plan_adopt(project_root, source, **plan["selection"])
    if canonical["stop_conditions"]:
        raise ApplyError(f"target changed since plan; stop conditions: {canonical['stop_conditions']}")
    if plan != canonical:
        raise ApplyError("plan changed since plan generation or differs from manifest; regenerate and review")
    changes = {}
    written = []
    unchanged = []
    for op in plan["files"]:
        relative = op["destination"]
        data = expected[relative]
        classification = op["classification"]
        _check_precondition(project_root, op, prepared, plan)
        if classification in ("EXISTS_KEEP", "PROJECT_OWNED", "UNCHANGED"):
            unchanged.append(relative)
            continue
        content = prepared[relative]
        if op.get("render"):
            content = _render_template(content, plan)
        if op["ownership"] == "managed-block":
            bounds = _block_bounds_bytes(content)
            if bounds is None:
                raise ApplyError(f"invalid source managed block: {relative}")
            begin, end = bounds
            block = content[begin:end]
            if classification == "ADD":
                content = _make_minimal_agents(content)
            else:
                bounds = _block_bounds_bytes(data)
                if bounds is None:
                    raise ApplyError(f"invalid target managed block: {relative}")
                begin, end = bounds
                content = data[:begin] + block + data[end:]
        changes[relative] = content
        written.append(relative)
    state = _build_state(plan, {**expected, **changes})
    # State is a fixed transaction step, never an arbitrary plan destination.
    changes[".themasterplan/state.json"] = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    apply_file_changes(project_root, changes, expected)
    return {"written": written, "unchanged": unchanged}
