from contextlib import contextmanager

import pytest

from backend import admin_accounts


def test_store_manager_is_not_a_supported_role():
    with pytest.raises(ValueError, match="Role must be one of: admin, manager, staff"):
        admin_accounts.create_account(
            1,
            "old-role",
            "old-role@example.com",
            "safe-password",
            "store_manager",
        )


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, admin, account):
        self.admin = admin
        self.account = account
        self.statements = []

    def execute(self, statement, params=()):
        self.statements.append((statement, params))
        if "SELECT role, is_active FROM" in statement:
            return FakeResult(self.admin)
        if 'FROM "Users" WHERE user_id = %s' in statement:
            return FakeResult(self.account)
        raise AssertionError(f"Unexpected SQL: {statement}")


@pytest.mark.parametrize("is_active", [True, False])
def test_admin_account_role_cannot_be_changed(monkeypatch, is_active):
    connection = FakeConnection(
        {"role": "admin", "is_active": True},
        {
            "user_id": 2,
            "username": "another-admin",
            "email": "admin@example.com",
            "role": "admin",
            "is_active": is_active,
        },
    )

    @contextmanager
    def connect_database(_database_url=None):
        yield connection

    monkeypatch.setattr(admin_accounts, "connect_database", connect_database)

    with pytest.raises(ValueError, match="Admin account roles cannot be changed"):
        admin_accounts.update_account(1, 2, {"role": "manager"})

    assert not any("UPDATE" in str(statement) for statement, _ in connection.statements)
