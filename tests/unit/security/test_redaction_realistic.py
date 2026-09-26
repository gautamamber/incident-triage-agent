"""Stress tests with messier, real-shaped payloads — the clean single-secret
strings in test_redaction.py prove the regex logic; these prove it survives
contact with what actually shows up in production logs: multi-secret lines,
stack traces, JSON blobs, and formatted card numbers with separators."""

from app.security.redaction import redact


def test_redacts_a_realistic_stack_trace_with_multiple_secret_types():
    trace = (
        "Traceback (most recent call last):\n"
        '  File "/app/api/payments.py", line 45, in create_payment\n'
        '    resp = httpx.post(url, headers={"Authorization": '
        '"Bearer sk-proj-abc123XYZ789LMNOP"})\n'
        "requests.exceptions.HTTPError: 401 Client Error for url: "
        "https://api.stripe.com/v1/charges?api_key=sk_test_51H8xJ2KaBcDeFgHiJk&amount=500\n"
    )
    result = redact(trace)
    assert "sk-proj-abc123XYZ789LMNOP" not in result
    assert "sk_test_51H8xJ2KaBcDeFgHiJk" not in result
    assert "api_key=<secret>" in result
    assert "line 45, in create_payment" in result  # non-secret content survives


def test_redacts_a_realistic_json_log_line_with_mixed_pii_and_secrets():
    line = (
        '{"level":"error","msg":"payment failed","customer_email":'
        '"jane.doe+test@example.co.uk","card":"4532015112830366",'
        '"dsn":"postgresql://payments_user:Sup3r$ecret!@db.internal.example.com:5432/payments"}'
    )
    result = redact(line)
    assert "jane.doe+test@example.co.uk" not in result
    assert "4532015112830366" not in result
    assert "Sup3r$ecret!" not in result
    assert "postgresql://payments_user:<secret>@db.internal.example.com:5432/payments" in result
    assert '"level":"error"' in result


def test_redacts_a_card_number_written_with_dashes():
    # How a human or a validation-error message actually writes a card
    # number — the plain \d{13,19} pattern never matches this, since the
    # dashes break it into four 4-digit runs.
    text = "Card declined: 4111-1111-1111-1111 insufficient funds"
    result = redact(text)
    assert "4111-1111-1111-1111" not in result
    assert "<card>" in result


def test_redacts_a_card_number_written_with_spaces():
    text = "cardNumber: 4111 1111 1111 1111 (Visa test card)"
    result = redact(text)
    assert "4111 1111 1111 1111" not in result
    assert "<card>" in result


def test_does_not_redact_a_dashed_run_that_fails_luhn():
    # Same shape as the dash test above, but the digits don't pass Luhn —
    # must be left alone, same guarantee the plain-digit-run test already
    # gives for a non-separated sequence.
    text = "Order reference: 1234-5678-9012-3456"
    assert redact(text) == text


def test_redacts_multiple_jwts_and_a_password_in_the_same_multiline_log():
    jwt1 = (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    jwt2 = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.AbCdEfGhIjKlMnOpQrStUvWxYz0123456789ABCDEF"
    log = (
        f"[auth] incoming token={jwt1}\n"
        f"[auth] refresh token={jwt2}\n"
        "[db] connecting with postgresql://svc:hunter2@10.0.0.5/orders\n"
    )
    result = redact(log)
    assert jwt1 not in result
    assert jwt2 not in result
    assert "hunter2" not in result
    assert result.count("<secret>") >= 3
