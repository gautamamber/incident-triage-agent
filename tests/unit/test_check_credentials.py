from app import check_credentials


def test_checks_skip_when_unconfigured(monkeypatch):
    monkeypatch.setattr(check_credentials.settings, "anthropic_api_key", "")
    monkeypatch.setattr(check_credentials.settings, "github_token", "")
    monkeypatch.setattr(check_credentials.settings, "github_repo", "")
    monkeypatch.setattr(check_credentials.settings, "slack_webhook_url", "")

    assert check_credentials.check_llm() == ("llm", None)
    assert check_credentials.check_github() == ("github", None)
    assert check_credentials.check_slack() == ("slack", None)
