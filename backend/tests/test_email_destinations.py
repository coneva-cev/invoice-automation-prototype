"""Unit tests for the email send-destination guardrails (resolve_send_plan).

This is the single authority that decides whether/how a send may proceed, so it
is tested exhaustively — especially the fail-closed and recipient-replacement
paths, since a wrong recipient is business-critical.
"""

from __future__ import annotations

from app.email.config import (
    build_send_mode_view,
    is_email_domain_allowed,
    resolve_app_mode,
    resolve_send_plan,
)

TEST = {"EMAIL_MODE": "test"}
LIVE = {"EMAIL_MODE": "live"}


# --- app mode resolution ---------------------------------------------------


def test_app_mode_explicit_wins():
    assert resolve_app_mode({"EMAIL_MODE": "live"}) == "live"
    assert resolve_app_mode({"EMAIL_MODE": "test"}) == "test"


def test_app_mode_derives_from_app_env_safely():
    assert resolve_app_mode({"APP_ENV": "production"}) == "live"
    assert resolve_app_mode({"APP_ENV": "local"}) == "test"
    assert resolve_app_mode({}) == "test"  # safe default


# --- domain check ----------------------------------------------------------


def test_domain_allow_list():
    assert is_email_domain_allowed("a@coneva.com", ["coneva.com"])
    assert not is_email_domain_allowed("a@evil.com", ["coneva.com"])
    assert not is_email_domain_allowed("a@sub.coneva.com", ["coneva.com"])
    assert not is_email_domain_allowed("no-at-sign", ["coneva.com"])
    assert not is_email_domain_allowed("@coneva.com", ["coneva.com"])
    assert not is_email_domain_allowed("a@b@coneva.com", ["coneva.com"])
    assert is_email_domain_allowed("A@CONEVA.COM", ["coneva.com"])  # case-insensitive


# --- test mode: replacement is forced + domain-checked ---------------------


def test_test_mode_all_destinations_replace_and_require_coneva():
    for kind in ("mailpit", "sendgrid_sandbox", "sendgrid_coneva"):
        p = resolve_send_plan(kind, "me@coneva.com", TEST)
        assert p.ok, (kind, p.error)
        assert p.replace_to == "me@coneva.com"
        assert p.delivers_real is False


def test_test_mode_rejects_non_coneva_replacement():
    p = resolve_send_plan("sendgrid_coneva", "me@gmail.com", TEST)
    assert not p.ok
    assert "must be an address in" in (p.error or "")


def test_test_mode_fail_closed_without_replacement():
    p = resolve_send_plan("mailpit", None, TEST)
    assert not p.ok
    p = resolve_send_plan("mailpit", "   ", TEST)
    assert not p.ok


def test_test_mode_forbids_live_destination():
    p = resolve_send_plan("sendgrid_live", "me@coneva.com", TEST)
    assert not p.ok
    assert "not permitted" in (p.error or "")


def test_test_mode_transport_and_sandbox_mapping():
    assert resolve_send_plan("mailpit", "me@coneva.com", TEST).backend == "smtp"
    sb = resolve_send_plan("sendgrid_sandbox", "me@coneva.com", TEST)
    assert sb.backend == "sendgrid" and sb.sandbox is True
    cv = resolve_send_plan("sendgrid_coneva", "me@coneva.com", TEST)
    assert cv.backend == "sendgrid" and cv.sandbox is False


# --- live mode: no replacement, real send gated ----------------------------


def test_live_mode_live_send_is_real_and_unreplaced():
    p = resolve_send_plan("sendgrid_live", None, LIVE)
    assert p.ok
    assert p.replace_to is None
    assert p.delivers_real is True
    assert p.backend == "sendgrid" and p.sandbox is False


def test_live_mode_sandbox_is_dry_run():
    p = resolve_send_plan("sendgrid_sandbox", None, LIVE)
    assert p.ok
    assert p.replace_to is None
    assert p.sandbox is True
    assert p.delivers_real is False


def test_live_mode_forbids_test_destinations():
    assert not resolve_send_plan("mailpit", None, LIVE).ok
    assert not resolve_send_plan("sendgrid_coneva", "me@coneva.com", LIVE).ok


# --- misc ------------------------------------------------------------------


def test_unknown_and_missing_destination_fail_closed():
    assert not resolve_send_plan(None, None, TEST).ok
    assert not resolve_send_plan("bogus", None, TEST).ok


def test_allowed_domains_configurable_but_never_empty():
    assert resolve_send_plan(
        "mailpit", "x@foo.io", {"EMAIL_MODE": "test", "EMAIL_TEST_ALLOWED_DOMAINS": "foo.io"}
    ).ok
    # Empty override falls back to the default coneva.com (never disabled).
    assert not resolve_send_plan(
        "mailpit", "x@foo.io", {"EMAIL_MODE": "test", "EMAIL_TEST_ALLOWED_DOMAINS": ""}
    ).ok


def test_mode_view_shape():
    v = build_send_mode_view({"EMAIL_MODE": "test", "EMAIL_TEST_RECIPIENTS": "me@coneva.com"})
    assert v["app_mode"] == "test"
    assert v["destinations"] == ["mailpit", "sendgrid_sandbox", "sendgrid_coneva"]
    assert v["test_default_recipient"] == "me@coneva.com"
    assert v["test_allowed_domains"] == ["coneva.com"]
    v2 = build_send_mode_view({"EMAIL_MODE": "live"})
    assert v2["destinations"] == ["sendgrid_sandbox", "sendgrid_live"]
