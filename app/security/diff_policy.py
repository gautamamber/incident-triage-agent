import re
from dataclasses import dataclass, field

from app.policies import load_policies

_FILE_HEADER_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.MULTILINE)
_HUNK_HEADER_RE = re.compile(r"^@@ ")
_SKIP_MARKER_RE = re.compile(r"@pytest\.mark\.skip|pytest\.skip\(|unittest\.skip")
_REMOVED_TEST_DEF_RE = re.compile(r"^-\s*(async\s+)?def test_")
_SUSPICIOUS_CALL_RE = re.compile(r"\b(subprocess\.|os\.system\(|eval\(|exec\()")


@dataclass
class DiffPolicyResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def touched_files(diff: str) -> list[str]:
    """The b/-side (post-patch) path of every file header in a unified diff —
    shared with fix.py, which needs this to know which files to write back
    through the GitHub Contents API after a patch is applied."""
    return [b_path for _a_path, b_path in _FILE_HEADER_RE.findall(diff)]


def check_diff(diff: str) -> DiffPolicyResult:
    """A whitelist, checked in code, on what an agent-generated patch is
    allowed to touch (doc section 11.5). This runs BEFORE the patch is ever
    applied for real — the LLM never gets a chance to argue its way past it,
    and a rejection here means the fix subgraph gives up on this attempt
    rather than silently loosening the check."""
    policies = load_policies()["fix"]
    reasons: list[str] = []

    files = touched_files(diff)

    if len(files) > policies["max_files"]:
        reasons.append(f"touches {len(files)} files, max allowed is {policies['max_files']}")

    for path in files:
        if not any(path.startswith(prefix) for prefix in policies["allowed_paths"]):
            reasons.append(f"{path} is outside the allowed paths {policies['allowed_paths']}")
        if any(denied in path for denied in policies["denied_paths"]):
            reasons.append(f"{path} matches a denied path pattern")

    changed_lines = 0
    for line in diff.splitlines():
        if line.startswith(("+++", "---")) or _HUNK_HEADER_RE.match(line):
            continue  # diff metadata, not an actual content change
        if line.startswith(("+", "-")):
            changed_lines += 1
        if line.startswith("+") and _SKIP_MARKER_RE.search(line):
            reasons.append(f"adds a test-skip marker: {line.strip()}")
        if _REMOVED_TEST_DEF_RE.match(line):
            reasons.append(f"removes a test function: {line.strip()}")
        if line.startswith("+") and _SUSPICIOUS_CALL_RE.search(line):
            reasons.append(f"adds a disallowed call: {line.strip()}")

    if changed_lines > policies["max_changed_lines"]:
        reasons.append(
            f"changes {changed_lines} lines, max allowed is {policies['max_changed_lines']}"
        )

    return DiffPolicyResult(allowed=not reasons, reasons=reasons)
