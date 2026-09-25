import base64

import httpx

from app.config import settings


def _headers() -> dict[str, str]:
    if not settings.github_token:
        raise RuntimeError("GITHUB_TOKEN not configured")
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _base_url() -> str:
    if not settings.github_repo:
        raise RuntimeError("GITHUB_REPO not configured")
    return f"https://api.github.com/repos/{settings.github_repo}"


def get_ref_sha(branch: str) -> str:
    resp = httpx.get(f"{_base_url()}/git/ref/heads/{branch}", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()["object"]["sha"]


def ensure_remote_branch(branch: str, base: str = "main") -> str:
    """Creates agent/INC-xxxx from base's current tip, or resets it there if
    it already exists (a retried attempt on the same incident starts clean —
    doc 9.1's idempotency requirement). This — not a local `git push` — is
    where the branch actually gets created; see repo_write.py's module
    docstring for why."""
    headers = _headers()
    base_url = _base_url()
    base_sha = get_ref_sha(base)

    create = httpx.post(
        f"{base_url}/git/refs",
        headers=headers,
        json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        timeout=15,
    )
    if create.status_code == 422:  # ref already exists
        reset = httpx.patch(
            f"{base_url}/git/refs/heads/{branch}",
            headers=headers,
            json={"sha": base_sha, "force": True},
            timeout=15,
        )
        reset.raise_for_status()
    else:
        create.raise_for_status()
    return base_sha


def put_file_content(branch: str, path: str, content: str, message: str) -> str:
    """Writes (creates or updates) one file directly on `branch` via the
    Contents API — the commit is made server-side by GitHub, never by a
    local `git commit`."""
    headers = _headers()
    base_url = _base_url()

    get_resp = httpx.get(
        f"{base_url}/contents/{path}", headers=headers, params={"ref": branch}, timeout=15
    )
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if get_resp.status_code == 200:
        payload["sha"] = get_resp.json()["sha"]

    put_resp = httpx.put(f"{base_url}/contents/{path}", headers=headers, json=payload, timeout=15)
    put_resp.raise_for_status()
    return put_resp.json()["commit"]["sha"]


def delete_file_content(branch: str, path: str, message: str) -> str:
    headers = _headers()
    base_url = _base_url()

    get_resp = httpx.get(
        f"{base_url}/contents/{path}", headers=headers, params={"ref": branch}, timeout=15
    )
    get_resp.raise_for_status()

    del_resp = httpx.request(
        "DELETE",
        f"{base_url}/contents/{path}",
        headers=headers,
        json={"message": message, "sha": get_resp.json()["sha"], "branch": branch},
        timeout=15,
    )
    del_resp.raise_for_status()
    return del_resp.json()["commit"]["sha"]


def create_draft_pr(branch: str, title: str, body: str, base: str = "main") -> str:
    """Opens a draft PR via the GitHub REST API (doc 7.3/9.4) — always
    draft=true, the agent never marks it ready or merges. Idempotent: if an
    open PR already exists for this branch, its title/body are updated
    instead of creating a duplicate (doc 9.1's 'no open agent PR already
    exists... otherwise update it')."""
    headers = _headers()
    base_url = _base_url()
    owner = settings.github_repo.split("/")[0]

    existing = httpx.get(
        f"{base_url}/pulls",
        headers=headers,
        params={"head": f"{owner}:{branch}", "state": "open"},
        timeout=15,
    )
    existing.raise_for_status()
    matches = existing.json()

    if matches:
        pr = matches[0]
        resp = httpx.patch(
            f"{base_url}/pulls/{pr['number']}",
            headers=headers,
            json={"title": title, "body": body},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["html_url"]

    resp = httpx.post(
        f"{base_url}/pulls",
        headers=headers,
        json={"title": title, "body": body, "head": branch, "base": base, "draft": True},
        timeout=15,
    )
    resp.raise_for_status()
    pr = resp.json()

    try:
        httpx.post(
            f"{base_url}/issues/{pr['number']}/labels",
            headers=headers,
            json={"labels": ["agent-generated", "incident"]},
            timeout=15,
        ).raise_for_status()
    except httpx.HTTPError:
        pass  # labels are cosmetic; a missing label must not fail the PR itself

    return pr["html_url"]
