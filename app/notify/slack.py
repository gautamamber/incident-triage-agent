import httpx

from app.config import settings


def post_slack(text: str) -> bool:
    """Posts to the incoming webhook. Returns False — never raises — if no
    webhook is configured, same skip-not-fail pattern as
    check_credentials.py: a missing Slack config shouldn't crash a run."""
    if not settings.slack_webhook_url:
        return False
    resp = httpx.post(settings.slack_webhook_url, json={"text": text}, timeout=10)
    resp.raise_for_status()
    return True
