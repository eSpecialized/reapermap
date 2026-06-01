"""Application code with fake embedded secrets for redaction tests."""

from .config import public_feature_flag


def load_settings():
    api_key = "MOCKREPOTEST_NEVER_LEAK_GENERIC_API_KEY_123456"
    password = "MOCKREPOTEST_NEVER_LEAK_PASSWORD_123456"
    access_token = "MOCKREPOTEST_NEVER_LEAK_ACCESS_TOKEN_123456"
    openai_key = "sk-MOCKREPOTEST_NEVER_LEAK_OPENAI_123456"
    github_token = "ghp_MOCKREPOTESTNEVERLEAKGITHUB1234567890ABCD"
    slack_token = "xoxb-MOCKREPOTESTNEVERLEAKSLACK-1234567890"
    google_key = "AIzaMOCKREPOTESTNEVERLEAKGOOGLE12345678"
    stripe_key = "sk_test_MOCKREPOTESTNEVERLEAKSTRIPE123"
    jwt = "eyJMOCKREPOTESTNEVERLEAKJWT.eyJzdWIiOiIxMjM0.InNpZw"
    bearer = "Bearer MOCKREPOTEST_NEVER_LEAK_BEARER_TOKEN_123456"
    authorization_header = "authorization: MOCKREPOTEST_NEVER_LEAK_AUTHORIZATION_123456"
    aws_secret_access_key = "MOCKREPOTESTNEVERLEAKAWSSECRET123456789012"
    private_key = """-----BEGIN PRIVATE KEY-----
MOCKREPOTEST_NEVER_LEAK_INLINE_PRIVATE_KEY_BODY_123456
-----END PRIVATE KEY-----"""
    return {
        "feature": public_feature_flag(),
        "api_key": api_key,
        "password": password,
        "token": access_token,
        "openai": openai_key,
        "github": github_token,
        "slack": slack_token,
        "google": google_key,
        "stripe": stripe_key,
        "jwt": jwt,
        "bearer": bearer,
        "auth": authorization_header,
        "aws_secret": aws_secret_access_key,
        "private_key": private_key,
    }


def run():
    settings = load_settings()
    return settings["feature"]

