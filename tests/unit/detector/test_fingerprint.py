from app.detector.fingerprint import fingerprint, normalize_message


def test_normalizes_uuid():
    assert (
        normalize_message("Payment not found: 8f1c2a34-56e7-49ab-8b12-abc123456789")
        == "Payment not found: <uuid>"
    )


def test_normalizes_integers_and_decimals():
    assert normalize_message("timeout after 30 seconds, retried 3 times") == (
        "timeout after <num> seconds, retried <num> times"
    )
    assert normalize_message("amount was 42.50") == "amount was <num>"


def test_normalizes_quoted_strings():
    assert normalize_message('column "customer_id" does not exist') == (
        "column <str> does not exist"
    )


def test_normalizes_email():
    assert normalize_message("failed to notify user@example.com") == (
        "failed to notify <email>"
    )


def test_collapses_repeated_whitespace():
    assert normalize_message("too   many    spaces") == "too many spaces"


def test_fingerprint_is_deterministic():
    a = fingerprint(
        service="payment-service",
        exception_type="AttributeError",
        message="'NoneType' object has no attribute 'status'",
        top_frame="app/api/payments.py:refund_payment",
    )
    b = fingerprint(
        service="payment-service",
        exception_type="AttributeError",
        message="'NoneType' object has no attribute 'status'",
        top_frame="app/api/payments.py:refund_payment",
    )
    assert a == b


def test_fingerprint_differs_by_top_frame():
    common = dict(
        service="payment-service",
        exception_type="AttributeError",
        message="'NoneType' object has no attribute 'status'",
    )
    a = fingerprint(**common, top_frame="app/api/payments.py:refund_payment")
    b = fingerprint(**common, top_frame="app/api/payments.py:get_payment")
    assert a != b


def test_fingerprint_treats_missing_exception_type_consistently():
    common = dict(
        service="payment-service",
        message="Payment not found: 8f1c2a34-56e7-49ab-8b12-abc123456789",
        top_frame="app/api/payments.py:get_payment",
    )
    a = fingerprint(**common, exception_type=None)
    b = fingerprint(**common, exception_type=None)
    assert a == b


def test_two_uuid_variants_collapse_to_the_same_fingerprint():
    """The doc's own worked example (section 5.2): two 'Payment not found' lines
    that differ only by UUID must fingerprint identically, so the detector
    counts them as the same recurring problem, not two unrelated ones."""
    common = dict(
        service="payment-service",
        exception_type=None,
        top_frame="app/api/payments.py:get_payment",
    )
    a = fingerprint(
        **common, message="Payment not found: 8f1c2a34-56e7-49ab-8b12-abc123456789"
    )
    b = fingerprint(
        **common, message="Payment not found: 2b9a5678-1234-49ab-8b12-abc987654321"
    )
    assert a == b
