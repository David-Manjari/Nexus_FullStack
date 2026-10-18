import os
import re

import pytest

from backend.app import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set"
)

# (method, rule) pairs that can answer without a session
PUBLIC = {
    ("GET", "/"),
    ("GET", "/health"),
    ("POST", "/session/login"),
    ("POST", "/session/logout"),
}


def _concrete(rule):
    return re.sub(
        r"<(?:(\w+):)?\w+>", lambda m: "1" if m.group(1) == "int" else "x", rule
    )


def _routes(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            yield method, rule.rule


def test_every_endpoint_requires_a_session():
    app = create_app(secret_key="test-secret-key")
    app.config.update(TESTING=True)
    client = app.test_client()

    checked, failures = 0, []
    for method, rule in _routes(app):
        if (method, rule) in PUBLIC:
            continue
        checked += 1
        response = client.open(_concrete(rule), method=method, json={})
        if response.status_code != 401:
            failures.append(f"{method} {rule} answered {response.status_code}")

    assert checked > 0, "No routes were checked."
    assert not failures, "Reachable without signing in:\n" + "\n".join(failures)