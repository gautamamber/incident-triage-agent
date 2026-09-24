from app.config import Settings


def test_default_agent_mode_is_rca():
    s = Settings(_env_file=None)
    assert s.agent_mode == "rca"


def test_agent_mode_rejects_invalid_value():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, agent_mode="delete_everything")
