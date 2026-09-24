from app.security.redaction import redact


def test_redacts_luhn_valid_card_number():
    # 4111111111111111 is the well-known Visa test number — real, Luhn-valid, never a live account.
    assert redact("card on file: 4111111111111111") == "card on file: <card>"


def test_does_not_redact_non_luhn_digit_run():
    """The whole point of this pass vs Phase 1's collector-level regex: a 16-digit
    number that just happens to be the right LENGTH but fails the Luhn checksum
    is not a card number and must be left alone."""
    text = "order reference: 1234567890123456"
    assert redact(text) == text


def test_redacts_email():
    assert redact("failed to notify user@example.com") == "failed to notify <email>"


def test_redacts_bearer_token():
    assert redact("Authorization: Bearer abc123.def456-ghi") == "Authorization: <secret>"


def test_redacts_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    assert redact(f"token={jwt}") == "token=<secret>"


def test_redacts_known_api_key_prefixes():
    assert redact("key: sk-abcdEFGH12345678") == "key: <secret>"
    assert redact("key: ghp_abcdEFGH12345678") == "key: <secret>"
    assert redact("key: AKIAABCDEFGHIJKLMNOP") == "key: <secret>"


def test_redacts_password_in_dsn():
    dsn = "postgresql://agent:supersecret@127.0.0.1:5432/agent"
    assert redact(dsn) == "postgresql://agent:<secret>@127.0.0.1:5432/agent"


def test_redacts_query_string_secret():
    url = "https://api.example.com/x?token=abc123&foo=bar"
    assert redact(url) == "https://api.example.com/x?token=<secret>&foo=bar"


def test_leaves_safe_text_untouched():
    text = "Payment not found: payment_id lookup returned zero rows"
    assert redact(text) == text
