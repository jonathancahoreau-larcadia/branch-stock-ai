"""Database model registration helpers."""


def load_models() -> None:
    """Import model declarations so they are registered in ``db.metadata``.

    Flask-Migrate and Alembic inspect the metadata owned by the initialized
    Flask-SQLAlchemy extension. Importing the declarations before migration
    commands inspect that metadata makes every mapped table discoverable,
    while keeping model imports out of ``extensions.py`` and avoiding an
    extension/model import cycle.
    """
    from . import models as _models  # noqa: F401


__all__ = ["load_models"]
