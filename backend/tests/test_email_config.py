"""Tests for APP_ENV-driven email backend resolution.

Note: delivery safety (test/live, recipient replacement, domain allow-list) is
NOT decided here — see test_email_destinations.py. This module only checks that
``resolve_email_config`` resolves the transport backend + sandbox defaults.
"""

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


def test_production_defaults_to_sendgrid_sandbox_off():
    cfg = resolve_email_config({"APP_ENV": "production"})
    assert cfg.backend == "sendgrid"
    assert cfg.sandbox is False
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
    cfg = resolve_email_config({"APP_ENV": "production", "SENDGRID_SANDBOX": "true"})
    assert cfg.sandbox is True
    cfg = resolve_email_config({"APP_ENV": "staging", "SENDGRID_SANDBOX": "false"})
    assert cfg.sandbox is False


def test_backend_and_sandbox_are_case_insensitive():
    cfg = resolve_email_config({"APP_ENV": "PRODUCTION", "EMAIL_BACKEND": "SendGrid"})
    assert cfg.app_env == "production"
    assert cfg.backend == "sendgrid"
