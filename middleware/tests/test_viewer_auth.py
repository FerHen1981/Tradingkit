"""Viewer auth must fail CLOSED.

Regression guard for D-01: with no VIEWER_PASSWORD the cockpit used to serve the whole
fleet — account numbers, balances, survival buffers, open positions — to anyone. Running
without auth is now an explicit choice (VIEWER_ALLOW_OPEN=1), never a default.
"""
import importlib
import os

import pytest


def _viewer(monkeypatch, **env):
    """Re-import app.viewer with a given environment (its auth config is module-level)."""
    for k in ("VIEWER_PASSWORD", "VIEWER_ALLOW_OPEN", "VIEWER_API_TOKEN", "VIEWER_SECRET"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.viewer as v
    return importlib.reload(v)


def test_no_password_denies_everything(monkeypatch):
    v = _viewer(monkeypatch)                          # nothing configured = the deployed mistake
    assert v._authed({}) is False
    assert v._api_authorized("/api/command", {}) is False
    assert v._api_authorized("/api/state", {}) is False


def test_allow_open_is_an_explicit_opt_in(monkeypatch):
    v = _viewer(monkeypatch, VIEWER_ALLOW_OPEN="1")   # local dev, deliberately open
    assert v._authed({}) is True
    for val in ("0", "false", "no", ""):
        assert _viewer(monkeypatch, VIEWER_ALLOW_OPEN=val)._authed({}) is False


def test_password_set_requires_the_session_cookie(monkeypatch):
    v = _viewer(monkeypatch, VIEWER_PASSWORD="s3cret")
    assert v._authed({}) is False
    assert v._authed({"Cookie": "mexsession=wrong"}) is False
    assert v._authed({"Cookie": f"mexsession={v._token()}"}) is True


def test_api_token_works_without_a_cookie_but_only_when_set(monkeypatch):
    v = _viewer(monkeypatch, VIEWER_PASSWORD="s3cret", VIEWER_API_TOKEN="widget-tok")
    assert v._api_authorized("/api/widget", {"X-Token": "widget-tok"}) is True
    assert v._api_authorized("/api/widget?token=widget-tok", {}) is True
    assert v._api_authorized("/api/widget", {"X-Token": "nope"}) is False


@pytest.fixture(autouse=True)
def _restore():
    """Leave app.viewer importable with the ambient environment for other tests."""
    yield
    os.environ.pop("VIEWER_ALLOW_OPEN", None)
    import app.viewer
    importlib.reload(app.viewer)
