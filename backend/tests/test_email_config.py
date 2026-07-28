"""Tests for APP_ENV-driven email backend resolution."""

from __future__ import annotations

from app.email.config import resolve_email_config


def test_local_defaults_to_smtp_no_sandbox():
    cfg = resolve_email_config({"APP_ENV": "local"})
    assert cfg.backend == "smtp"
    assert cfg.sandbox is False


def test_staging_defaults_to_sendgrid_sandbox_on():
    cfg = resolve_email_config({"APP_ENV": "staging"})
    assert cfg.backend == "sendgrid"
    assert cfg.sandbox is True


def test_production_without_opt_in_is_forced_to_sandbox():
    # Fail-closed: production selects sendgrid, but without the real-send
    # opt-in it must NOT deliver — forced back into sandbox.
    cfg = resolve_email_config({"APP_ENV": "production"})
    assert cfg.backend == "sendgrid"
    assert cfg.sandbox is True
    assert cfg.real_send_blocked is True
    assert cfg.delivers is False


def test_production_with_opt_in_delivers():
    cfg = resolve_email_config(
        {"APP_ENV": "production", "EMAIL_ALLOW_REAL_SEND": "true"}
    )
    assert cfg.backend == "sendgrid"
    assert cfg.sandbox is False
    assert cfg.real_send_blocked is False
    assert cfg.delivers is True


def test_missing_app_env_falls_back_to_local():
    cfg = resolve_email_config({})
    assert cfg.app_env == "local"
    assert cfg.backend == "smtp"


def test_unknown_app_env_falls_back_to_local():
    cfg = resolve_email_config({"APP_ENV": "weird"})
    assert cfg.backend == "smtp"
    assert cfg.sandbox is False


def test_explicit_backend_overrides_app_env():
    cfg = resolve_email_config({"APP_ENV": "production", "EMAIL_BACKEND": "console"})
    assert cfg.backend == "console"


def test_explicit_sandbox_overrides_app_env():
    # production + explicit sandbox true -> sandbox (no delivery), no opt-in needed.
    cfg = resolve_email_config(
        {"APP_ENV": "production", "SENDGRID_SANDBOX": "true"}
    )
    assert cfg.sandbox is True
    # staging + explicit sandbox false, but WITH the real-send opt-in -> delivers.
    cfg = resolve_email_config(
        {
            "APP_ENV": "staging",
            "SENDGRID_SANDBOX": "false",
            "EMAIL_ALLOW_REAL_SEND": "true",
        }
    )
    assert cfg.sandbox is False
    assert cfg.delivers is True


def test_sandbox_off_without_opt_in_is_still_blocked():
    # Even explicitly turning sandbox off does not deliver without the opt-in.
    cfg = resolve_email_config(
        {"APP_ENV": "staging", "SENDGRID_SANDBOX": "false"}
    )
    assert cfg.sandbox is True
    assert cfg.real_send_blocked is True
    assert cfg.delivers is False


def test_backend_and_sandbox_are_case_insensitive():
    cfg = resolve_email_config({"APP_ENV": "PRODUCTION", "EMAIL_BACKEND": "SendGrid"})
    assert cfg.app_env == "production"
    assert cfg.backend == "sendgrid"
