"""Tests for Backoffice application creation."""

from flask import Flask


def test_application_starts(app):
    """The application factory returns a configured Flask application."""
    assert isinstance(app, Flask)
    assert app.testing is True
