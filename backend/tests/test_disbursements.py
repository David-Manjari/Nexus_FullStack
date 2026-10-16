import pytest

from backend.app import create_app


@pytest.fixture
def app():
    """Create a Flask application for testing."""
    application = create_app()
    application.config.update(TESTING=True)
    yield application


@pytest.fixture
def client(app):
    """Provide a test client for HTTP requests."""
    return app.test_client()


def test_app_starts(client):
    """The Flask test client should be available."""
    assert client is not None


def test_disbursement_routes_are_registered(app):
    """At least one disbursement-related route must exist."""
    routes = [
        rule.rule
        for rule in app.url_map.iter_rules()
        if any(
            word in rule.rule.lower()
            for word in ("disbursement", "disbursements", "payout", "payouts")
        )
    ]

    assert routes, "No disbursement or payout routes are registered"


def test_disbursement_endpoints_respond(client):
    """Registered static GET endpoints should not return server errors."""
    app = client.application

    routes = [
        rule
        for rule in app.url_map.iter_rules()
        if any(
            word in rule.rule.lower()
            for word in ("disbursement", "disbursements", "payout", "payouts")
        )
        and "GET" in rule.methods
        and "<" not in rule.rule
    ]

    assert routes, "No static GET disbursement or payout endpoints found"

    for rule in routes:
        response = client.get(rule.rule)
        assert response.status_code < 500, (
            f"GET {rule.rule} returned server error "
            f"{response.status_code}: {response.get_data(as_text=True)}"
        )
