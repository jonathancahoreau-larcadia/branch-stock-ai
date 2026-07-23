"""SQLAlchemy models for the Backoffice PostgreSQL schema."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backoffice.extensions import db

ADMIN_ROLE = "admin"
COMMON_USER_ROLE = "common_user"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _utc_now() -> datetime:
    """Return an aware UTC timestamp for SQLAlchemy-side defaults."""
    return datetime.now(timezone.utc)


class Branch(db.Model):
    """A physical branch containing users and stock records."""

    __tablename__ = "branches"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_branches"),
        UniqueConstraint("name", name="uq_branches_name"),
        CheckConstraint(
            "char_length(btrim(name)) > 0",
            name="ck_branches_name_not_blank",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
        onupdate=_utc_now,
    )

    users: Mapped[list[User]] = relationship(
        back_populates="branch",
        passive_deletes=True,
    )
    stocks: Mapped[list[Stock]] = relationship(
        back_populates="branch",
        passive_deletes=True,
    )


class User(db.Model):
    """A Backoffice administrator or branch-scoped common user."""

    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_users"),
        UniqueConstraint("username", name="uq_users_username"),
        CheckConstraint(
            "char_length(btrim(username)) > 0",
            name="ck_users_username_not_blank",
        ),
        CheckConstraint(
            "role IN ('admin', 'common_user')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "(role = 'admin' AND branch_id IS NULL) OR "
            "(role = 'common_user' AND branch_id IS NOT NULL)",
            name="ck_users_branch_assignment",
        ),
        CheckConstraint(
            "role <> 'admin' OR username = 'admin'",
            name="ck_users_admin_username",
        ),
        CheckConstraint(
            "username <> 'admin' OR role = 'admin'",
            name="ck_users_reserved_admin_username",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR is_active = FALSE",
            name="ck_users_soft_delete_state",
        ),
        CheckConstraint(
            "token_version >= 0",
            name="ck_users_token_version_non_negative",
        ),
        Index("ix_users_branch_id", "branch_id"),
        Index("ix_users_active", "is_active"),
        Index(
            "uq_users_single_admin",
            "role",
            unique=True,
            postgresql_where=text("role = 'admin'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=COMMON_USER_ROLE,
        server_default=text("'common_user'"),
    )
    branch_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "branches.id",
            name="fk_users_branch_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
        onupdate=_utc_now,
    )

    branch: Mapped[Branch | None] = relationship(back_populates="users")
    revoked_tokens: Mapped[list[RevokedToken]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )


class Stock(db.Model):
    """The quantity of an externally managed product in one branch."""

    __tablename__ = "stocks"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_stocks"),
        UniqueConstraint(
            "branch_id",
            "external_product_id",
            name="uq_stocks_branch_product",
        ),
        CheckConstraint(
            "char_length(btrim(external_product_id)) > 0",
            name="ck_stocks_external_product_id_not_blank",
        ),
        CheckConstraint(
            "quantity >= 0",
            name="ck_stocks_quantity_non_negative",
        ),
        Index("ix_stocks_external_product_id", "external_product_id"),
        Index("ix_stocks_branch_quantity", "branch_id", "quantity"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "branches.id",
            name="fk_stocks_branch_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    external_product_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
        onupdate=_utc_now,
    )

    branch: Mapped[Branch] = relationship(back_populates="stocks")


class RevokedToken(db.Model):
    """A revoked JWT identifier stored without the complete token."""

    __tablename__ = "revoked_tokens"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_revoked_tokens"),
        UniqueConstraint("jti", name="uq_revoked_tokens_jti"),
        CheckConstraint(
            "char_length(btrim(jti)) > 0",
            name="ck_revoked_tokens_jti_not_blank",
        ),
        CheckConstraint(
            "token_type IN ('access', 'refresh')",
            name="ck_revoked_tokens_type",
        ),
        Index("ix_revoked_tokens_expires_at", "expires_at"),
        Index("ix_revoked_tokens_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id",
            name="fk_revoked_tokens_user_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    jti: Mapped[str] = mapped_column(String(255), nullable=False)
    token_type: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    user: Mapped[User] = relationship(back_populates="revoked_tokens")


__all__ = ["Branch", "RevokedToken", "Stock", "User"]
