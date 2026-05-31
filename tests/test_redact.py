"""Redaction tests."""

from privrepomap.redact import redact


def test_aws_key_redacted():
    assert "AKIAIOSFODNN7EXAMPLE" not in redact("key=AKIAIOSFODNN7EXAMPLE")


def test_generic_api_key_redacted():
    out = redact("api_key = 'hunter2hunter2'")
    assert "hunter2hunter2" not in out
    assert "[REDACTED]" in out


def test_jwt_redacted():
    jwt = "eyJhbGciOi.eyJzdWIiOiAxMjM0.SflKxwRJSMeKKF2QT4"
    assert jwt not in redact(f"token: {jwt}")


def test_private_key_body_redacted():
    pem = "-----BEGIN PRIVATE KEY-----\nMIIBVgIBADAN\n-----END PRIVATE KEY-----"
    out = redact(pem)
    assert "MIIBVgIBADAN" not in out
    assert "BEGIN PRIVATE KEY" in out


def test_plain_text_untouched():
    text = "def hello():\n    return 1\n"
    assert redact(text) == text
