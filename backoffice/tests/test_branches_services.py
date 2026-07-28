"""Unit tests for branch consultation business rules."""

import pytest

from backoffice.branches.services import (
    BranchAccessForbiddenError,
    BranchNotFoundError,
    BranchRoleForbiddenError,
    get_accessible_branch,
    list_accessible_branches,
    serialize_branch,
)
from backoffice.database.models import (
    ADMIN_ROLE,
    COMMON_USER_ROLE,
    Branch,
    User,
)


def _user(*, role, branch_id=None):
    return User(
        id=1,
        username="admin" if role == ADMIN_ROLE else "alice",
        password_hash="not-returned",
        role=role,
        branch_id=branch_id,
        is_active=True,
        token_version=0,
    )


def test_serialize_branch_uses_an_exact_public_whitelist():
    branch = Branch(id=2, name="Toulon")

    assert serialize_branch(branch) == {"id": 2, "name": "Toulon"}


def test_admin_lists_every_branch_in_repository_order(monkeypatch):
    branches = [
        Branch(id=3, name="Marseille"),
        Branch(id=2, name="Toulon"),
    ]
    monkeypatch.setattr(
        "backoffice.branches.repositories.list_branches",
        lambda: branches,
    )

    assert list_accessible_branches(_user(role=ADMIN_ROLE)) == branches


def test_common_user_lists_only_their_current_branch(monkeypatch):
    branch = Branch(id=2, name="Toulon")
    requested_ids = []

    def get_branch(branch_id):
        requested_ids.append(branch_id)
        return branch

    monkeypatch.setattr(
        "backoffice.branches.repositories.get_branch",
        get_branch,
    )

    result = list_accessible_branches(
        _user(role=COMMON_USER_ROLE, branch_id=2)
    )

    assert result == [branch]
    assert requested_ids == [2]


def test_common_user_foreign_scope_is_rejected_before_lookup(monkeypatch):
    def unexpected_lookup(_branch_id):
        raise AssertionError("A foreign branch must not be looked up.")

    monkeypatch.setattr(
        "backoffice.branches.repositories.get_branch",
        unexpected_lookup,
    )

    with pytest.raises(BranchAccessForbiddenError):
        get_accessible_branch(
            _user(role=COMMON_USER_ROLE, branch_id=2),
            999,
        )


def test_admin_receives_not_found_for_an_unknown_branch(monkeypatch):
    monkeypatch.setattr(
        "backoffice.branches.repositories.get_branch",
        lambda _branch_id: None,
    )

    with pytest.raises(BranchNotFoundError):
        get_accessible_branch(_user(role=ADMIN_ROLE), 999)


@pytest.mark.parametrize("operation", ["list", "detail"])
def test_unknown_database_role_is_forbidden(monkeypatch, operation):
    user = _user(role="unexpected_role", branch_id=2)

    if operation == "list":
        with pytest.raises(BranchRoleForbiddenError):
            list_accessible_branches(user)
    else:
        with pytest.raises(BranchRoleForbiddenError):
            get_accessible_branch(user, 2)


def test_common_user_without_a_resolvable_branch_is_not_found(monkeypatch):
    user = _user(role=COMMON_USER_ROLE, branch_id=2)
    monkeypatch.setattr(
        "backoffice.branches.repositories.get_branch",
        lambda _branch_id: None,
    )

    with pytest.raises(BranchNotFoundError):
        list_accessible_branches(user)
