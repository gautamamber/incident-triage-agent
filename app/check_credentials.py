import httpx

from app.config import settings


def check_llm() -> tuple[str, bool | None]:
    if not settings.anthropic_api_key:
        return "llm", None
    resp = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        },
        timeout=10,
    )
    return "llm", resp.status_code == 200


def check_github() -> tuple[str, bool | None]:
    if not settings.github_token or not settings.github_repo:
        return "github", None
    resp = httpx.get(
        f"https://api.github.com/repos/{settings.github_repo}",
        headers={"Authorization": f"Bearer {settings.github_token}"},
        timeout=10,
    )
    return "github", resp.status_code == 200


def check_slack() -> tuple[str, bool | None]:
    if not settings.slack_webhook_url:
        return "slack", None
    resp = httpx.post(
        settings.slack_webhook_url,
        json={"text": "incident-triage-agent: credentials check OK"},
        timeout=10,
    )
    return "slack", resp.status_code == 200 and resp.text == "ok"


def main() -> None:
    checks = [check_llm, check_github, check_slack]
    all_ok = True
    for check in checks:
        name, ok = check()
        if ok is None:
            print(f"{name}: SKIP (not configured)")
        elif ok:
            print(f"{name}: PASS")
        else:
            print(f"{name}: FAIL")
            all_ok = False
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
