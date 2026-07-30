"""Transactional CLI command for rotating the unique admin password."""

from __future__ import annotations

import os

import click
from flask.cli import with_appcontext
from sqlalchemy import or_, select

from backoffice.config import validate_runtime_value
from backoffice.database.models import ADMIN_ROLE, User
from backoffice.extensions import db
from backoffice.users.services import hash_password


def _validated_password(value: object) -> str:
    try:
        password = validate_runtime_value("ADMIN_INITIAL_PASSWORD", value)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None
    if len(password.encode("utf-8")) > 72:
        raise click.ClickException(
            "ADMIN_INITIAL_PASSWORD exceeds the bcrypt UTF-8 byte limit."
        )
    return password


def _load_unique_admin() -> User:
    candidates = list(
        db.session.scalars(
            select(User)
            .where(or_(User.role == ADMIN_ROLE, User.username == "admin"))
            .with_for_update()
        ).all()
    )
    if len(candidates) != 1:
        raise click.ClickException(
            "The unique admin account is absent or inconsistent."
        )
    admin = candidates[0]
    if not (
        admin.username == "admin"
        and admin.role == ADMIN_ROLE
        and admin.branch_id is None
        and admin.is_active is True
        and admin.deleted_at is None
        and isinstance(admin.token_version, int)
        and not isinstance(admin.token_version, bool)
        and admin.token_version >= 0
    ):
        raise click.ClickException(
            "The unique admin account is absent or inconsistent."
        )
    return admin


@click.command("admin-password")
@with_appcontext
def admin_password_command() -> None:
    """Rotate the unique admin password and invalidate its existing tokens."""
    password = _validated_password(os.environ.get("ADMIN_INITIAL_PASSWORD"))
    try:
        admin = _load_unique_admin()
        admin.password_hash = hash_password(password)
        admin.token_version += 1
        db.session.flush()
        db.session.commit()
    except click.ClickException:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        raise click.ClickException(
            "The admin password update failed transactionally."
        ) from exc
    click.echo("The admin password was updated and prior tokens were invalidated.")


__all__ = ["admin_password_command"]
