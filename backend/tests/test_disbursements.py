import pytest

from backend.app import create_app
from backend.services.disbursements import _approved_disbursement


class FakeApprovalConnection:
    def __init__(self, approval):
        self.approval = approval

    def execute(self, statement, params):
        assert "FROM \"Approval_Items\"" in statement
        assert params == (42,)
        return self

    def fetchone(self):
        return self.approval


def test_approver_can_submit_their_approved_disbursement():
    approval = {"requested_by": 7, "decided_by": 9}

    _approved_disbursement(FakeApprovalConnection(approval), 42)


def test_requester_still_cannot_approve_their_own_disbursement():
    approval = {"requested_by": 9, "decided_by": 9}

    with pytest.raises(ValueError, match="requester cannot approve"):
        _approved_disbursement(FakeApprovalConnection(approval), 42)


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
