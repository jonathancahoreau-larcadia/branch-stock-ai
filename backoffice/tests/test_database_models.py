"""Structural tests for the Backoffice SQLAlchemy model declarations.

These tests inspect mappings and compile PostgreSQL DDL. They intentionally do
not use SQLite writes as evidence that PostgreSQL constraints behave correctly.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    UniqueConstraint,
    inspect,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from backoffice.database import models
from backoffice.database.models import Branch, RevokedToken, Stock, User
from backoffice.extensions import db


def _constraint_names(table, constraint_type):
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, constraint_type)
    }


def _postgresql_table_ddl(table) -> str:
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_expected_models_are_registered_in_metadata(app):
    """Loading the application registers only the four local data tables."""
    with app.app_context():
        assert set(db.metadata.tables) == {
            "branches",
            "users",
            "stocks",
            "revoked_tokens",
        }

    assert not hasattr(models, "Product")
    assert "products" not in db.metadata.tables


def test_models_declare_the_exact_columns():
    """Every model exposes the documented columns and no product details."""
    assert list(Branch.__table__.columns.keys()) == [
        "id",
        "name",
        "created_at",
        "updated_at",
    ]
    assert list(User.__table__.columns.keys()) == [
        "id",
        "username",
        "password_hash",
        "role",
        "branch_id",
        "is_active",
        "token_version",
        "deleted_at",
        "created_at",
        "updated_at",
    ]
    assert list(Stock.__table__.columns.keys()) == [
        "id",
        "branch_id",
        "external_product_id",
        "quantity",
        "created_at",
        "updated_at",
    ]
    assert list(RevokedToken.__table__.columns.keys()) == [
        "id",
        "user_id",
        "jti",
        "token_type",
        "expires_at",
        "revoked_at",
        "reason",
    ]


def test_identifiers_use_big_integer_identity_and_named_primary_keys():
    """Every identifier is a generated BIGINT with an explicit PK name."""
    expected_primary_keys = {
        Branch: "pk_branches",
        User: "pk_users",
        Stock: "pk_stocks",
        RevokedToken: "pk_revoked_tokens",
    }

    for model, primary_key_name in expected_primary_keys.items():
        identifier = model.__table__.c.id
        assert isinstance(identifier.type, BigInteger)
        assert isinstance(identifier.identity, Identity)
        assert identifier.primary_key is True
        assert model.__table__.primary_key.name == primary_key_name


def test_string_lengths_and_column_nullability_are_documented():
    """String sizes and conditionally nullable fields match the schema."""
    assert Branch.__table__.c.name.type.length == 120
    assert User.__table__.c.username.type.length == 80
    assert User.__table__.c.password_hash.type.length == 255
    assert User.__table__.c.role.type.length == 20
    assert Stock.__table__.c.external_product_id.type.length == 255
    assert RevokedToken.__table__.c.jti.type.length == 255
    assert RevokedToken.__table__.c.token_type.type.length == 20
    assert RevokedToken.__table__.c.reason.type.length == 50

    assert User.__table__.c.branch_id.nullable is True
    assert User.__table__.c.deleted_at.nullable is True
    assert RevokedToken.__table__.c.reason.nullable is True
    assert Stock.__table__.c.branch_id.nullable is False
    assert Stock.__table__.c.external_product_id.nullable is False
    assert Stock.__table__.c.quantity.nullable is False


def test_datetime_columns_are_timezone_aware_and_have_explicit_defaults():
    """TIMESTAMPTZ fields distinguish ORM defaults from server defaults."""
    defaulted_datetime_columns = [
        Branch.__table__.c.created_at,
        Branch.__table__.c.updated_at,
        User.__table__.c.created_at,
        User.__table__.c.updated_at,
        Stock.__table__.c.created_at,
        Stock.__table__.c.updated_at,
        RevokedToken.__table__.c.revoked_at,
    ]
    all_datetime_columns = [
        *defaulted_datetime_columns,
        User.__table__.c.deleted_at,
        RevokedToken.__table__.c.expires_at,
    ]

    for column in all_datetime_columns:
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is True

    for column in defaulted_datetime_columns:
        assert column.default is not None
        assert column.server_default is not None
        assert str(column.server_default.arg) == "now()"

    for model in (Branch, User, Stock):
        assert model.__table__.c.updated_at.onupdate is not None


def test_scalar_defaults_exist_on_both_sqlalchemy_and_postgresql_sides():
    """Core scalar defaults are not dependent on Python-only behavior."""
    expected_defaults = {
        User.__table__.c.role: ("common_user", "'common_user'"),
        User.__table__.c.is_active: (True, "true"),
        User.__table__.c.token_version: (0, "0"),
        Stock.__table__.c.quantity: (0, "0"),
    }

    for column, (python_default, server_default) in expected_defaults.items():
        assert column.default is not None
        assert column.default.arg == python_default
        assert column.server_default is not None
        assert str(column.server_default.arg) == server_default


def test_foreign_keys_are_named_and_restrict_physical_deletion():
    """All local ownership references delegate delete protection to SQL."""
    expected_foreign_keys = {
        User.__table__.c.branch_id: (
            "fk_users_branch_id",
            "branches.id",
        ),
        Stock.__table__.c.branch_id: (
            "fk_stocks_branch_id",
            "branches.id",
        ),
        RevokedToken.__table__.c.user_id: (
            "fk_revoked_tokens_user_id",
            "users.id",
        ),
    }

    for column, (constraint_name, target) in expected_foreign_keys.items():
        foreign_key = next(iter(column.foreign_keys))
        assert foreign_key.constraint.name == constraint_name
        assert foreign_key.target_fullname == target
        assert foreign_key.ondelete == "RESTRICT"


def test_unique_constraints_are_explicitly_named():
    """Business keys are represented by named table constraints."""
    assert _constraint_names(Branch.__table__, UniqueConstraint) == {
        "uq_branches_name"
    }
    assert _constraint_names(User.__table__, UniqueConstraint) == {
        "uq_users_username"
    }
    assert _constraint_names(Stock.__table__, UniqueConstraint) == {
        "uq_stocks_branch_product"
    }
    assert _constraint_names(RevokedToken.__table__, UniqueConstraint) == {
        "uq_revoked_tokens_jti"
    }

    stock_unique = next(
        constraint
        for constraint in Stock.__table__.constraints
        if constraint.name == "uq_stocks_branch_product"
    )
    assert list(stock_unique.columns.keys()) == [
        "branch_id",
        "external_product_id",
    ]


def test_check_constraints_are_explicitly_named():
    """Database-level invariants are all present in model metadata."""
    assert _constraint_names(Branch.__table__, CheckConstraint) == {
        "ck_branches_name_not_blank"
    }
    assert _constraint_names(User.__table__, CheckConstraint) == {
        "ck_users_username_not_blank",
        "ck_users_role",
        "ck_users_branch_assignment",
        "ck_users_admin_username",
        "ck_users_reserved_admin_username",
        "ck_users_soft_delete_state",
        "ck_users_token_version_non_negative",
    }
    assert _constraint_names(Stock.__table__, CheckConstraint) == {
        "ck_stocks_external_product_id_not_blank",
        "ck_stocks_quantity_non_negative",
    }
    assert _constraint_names(RevokedToken.__table__, CheckConstraint) == {
        "ck_revoked_tokens_jti_not_blank",
        "ck_revoked_tokens_type",
    }


def test_all_constraints_and_indexes_have_explicit_names():
    """Alembic will never need to infer a database object name."""
    for table in db.metadata.tables.values():
        assert all(constraint.name for constraint in table.constraints)
        assert all(index.name for index in table.indexes)


def test_indexes_match_query_and_uniqueness_requirements():
    """Index columns, uniqueness, and the admin predicate are explicit."""
    expected_indexes = {
        "users": {
            "ix_users_branch_id": (["branch_id"], False),
            "ix_users_active": (["is_active"], False),
            "uq_users_single_admin": (["role"], True),
        },
        "stocks": {
            "ix_stocks_external_product_id": (
                ["external_product_id"],
                False,
            ),
            "ix_stocks_branch_quantity": (
                ["branch_id", "quantity"],
                False,
            ),
        },
        "revoked_tokens": {
            "ix_revoked_tokens_expires_at": (["expires_at"], False),
            "ix_revoked_tokens_user_id": (["user_id"], False),
        },
    }

    for table_name, index_expectations in expected_indexes.items():
        indexes = {
            index.name: index
            for index in db.metadata.tables[table_name].indexes
        }
        assert set(indexes) == set(index_expectations)
        for index_name, (columns, unique) in index_expectations.items():
            assert list(indexes[index_name].columns.keys()) == columns
            assert indexes[index_name].unique is unique

    admin_index = next(
        index
        for index in User.__table__.indexes
        if index.name == "uq_users_single_admin"
    )
    predicate = admin_index.dialect_options["postgresql"]["where"]
    assert str(predicate) == "role = 'admin'"


def test_relationships_are_bidirectional_and_do_not_delete_dependents():
    """ORM relationships mirror RESTRICT ownership without delete cascades."""
    branch_relationships = inspect(Branch).relationships
    user_relationships = inspect(User).relationships
    stock_relationships = inspect(Stock).relationships
    token_relationships = inspect(RevokedToken).relationships

    assert branch_relationships.users.back_populates == "branch"
    assert branch_relationships.users.passive_deletes is True
    assert branch_relationships.stocks.back_populates == "branch"
    assert branch_relationships.stocks.passive_deletes is True
    assert user_relationships.branch.back_populates == "users"
    assert user_relationships.revoked_tokens.back_populates == "user"
    assert user_relationships.revoked_tokens.passive_deletes is True
    assert stock_relationships.branch.back_populates == "stocks"
    assert token_relationships.user.back_populates == "revoked_tokens"

    assert "delete" not in branch_relationships.users.cascade
    assert "delete" not in branch_relationships.stocks.cascade
    assert "delete" not in user_relationships.revoked_tokens.cascade


def test_models_compile_to_expected_postgresql_ddl():
    """The metadata renders PostgreSQL identities, TIMESTAMPTZ, and checks."""
    ddl = "\n".join(
        _postgresql_table_ddl(table)
        for table in (
            Branch.__table__,
            User.__table__,
            Stock.__table__,
            RevokedToken.__table__,
        )
    )

    assert ddl.count("GENERATED BY DEFAULT AS IDENTITY") == 4
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "CONSTRAINT ck_users_branch_assignment CHECK" in ddl
    assert "CONSTRAINT ck_users_token_version_non_negative CHECK" in ddl
    assert "CONSTRAINT ck_stocks_quantity_non_negative CHECK" in ddl
    assert "CONSTRAINT uq_stocks_branch_product UNIQUE" in ddl
    assert "CONSTRAINT uq_revoked_tokens_jti UNIQUE" in ddl
    assert ddl.count("ON DELETE RESTRICT") == 3

    admin_index = next(
        index
        for index in User.__table__.indexes
        if index.name == "uq_users_single_admin"
    )
    admin_index_ddl = str(
        CreateIndex(admin_index).compile(dialect=postgresql.dialect())
    )
    assert admin_index_ddl == (
        "CREATE UNIQUE INDEX uq_users_single_admin ON users (role) "
        "WHERE role = 'admin'"
    )
