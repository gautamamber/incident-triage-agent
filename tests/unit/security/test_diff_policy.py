from app.security.diff_policy import check_diff

_GOOD_DIFF = """\
diff --git a/app/api/payments.py b/app/api/payments.py
index e3a762b..255e25f 100644
--- a/app/api/payments.py
+++ b/app/api/payments.py
@@ -64,6 +64,9 @@ def refund_payment(payment_id: str, db: Session = Depends(get_db)):
     payment = db.get(Payment, payment_id)
+    if payment is None:
+        logger.warning("Payment not found: %s", payment_id)
+        raise HTTPException(status_code=404, detail="Payment not found")
     payment.status = "refunded"
"""


def test_allows_a_small_patch_inside_app():
    result = check_diff(_GOOD_DIFF)
    assert result.allowed
    assert result.reasons == []


def test_rejects_a_patch_touching_pyproject_toml():
    diff = """\
diff --git a/pyproject.toml b/pyproject.toml
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1,1 +1,2 @@
+evil = "dependency"
"""
    result = check_diff(diff)
    assert not result.allowed
    assert any("pyproject.toml" in r for r in result.reasons)


def test_rejects_a_patch_outside_app_and_tests():
    diff = """\
diff --git a/scripts/deploy.sh b/scripts/deploy.sh
--- a/scripts/deploy.sh
+++ b/scripts/deploy.sh
@@ -1,1 +1,2 @@
+echo hacked
"""
    result = check_diff(diff)
    assert not result.allowed
    assert any("outside the allowed paths" in r for r in result.reasons)


def test_rejects_too_many_changed_lines():
    added_lines = "\n".join(f"+line{i} = {i}" for i in range(100))
    diff = f"""\
diff --git a/app/big.py b/app/big.py
--- a/app/big.py
+++ b/app/big.py
@@ -1,1 +1,100 @@
{added_lines}
"""
    result = check_diff(diff)
    assert not result.allowed
    assert any("max allowed is" in r for r in result.reasons)


def test_rejects_a_test_skip_marker():
    diff = """\
diff --git a/tests/test_payments.py b/tests/test_payments.py
--- a/tests/test_payments.py
+++ b/tests/test_payments.py
@@ -1,1 +1,2 @@
+@pytest.mark.skip(reason="flaky")
 def test_refund():
"""
    result = check_diff(diff)
    assert not result.allowed
    assert any("test-skip marker" in r for r in result.reasons)


def test_rejects_removing_a_test_function():
    diff = """\
diff --git a/tests/test_payments.py b/tests/test_payments.py
--- a/tests/test_payments.py
+++ b/tests/test_payments.py
@@ -1,3 +1,1 @@
-def test_refund_missing_payment():
-    assert True
"""
    result = check_diff(diff)
    assert not result.allowed
    assert any("removes a test function" in r for r in result.reasons)


def test_rejects_a_subprocess_call():
    diff = """\
diff --git a/app/api/payments.py b/app/api/payments.py
--- a/app/api/payments.py
+++ b/app/api/payments.py
@@ -1,1 +1,2 @@
+subprocess.run(["rm", "-rf", "/"])
"""
    result = check_diff(diff)
    assert not result.allowed
    assert any("disallowed call" in r for r in result.reasons)


def test_rejects_too_many_files():
    diff = "\n".join(
        f"""\
diff --git a/app/file{i}.py b/app/file{i}.py
--- a/app/file{i}.py
+++ b/app/file{i}.py
@@ -1,1 +1,2 @@
+x = {i}
"""
        for i in range(5)
    )
    result = check_diff(diff)
    assert not result.allowed
    assert any("touches" in r and "files" in r for r in result.reasons)
