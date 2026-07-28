"""Environment-driven email backend resolution.

``APP_ENV`` picks sensible defaults for the email transport; explicit env vars
still win so any environment can be overridden without code changes.

    APP_ENV       backend    sandbox   delivers?
    ------------  ---------  --------  ----------------------------
    local         smtp       -         no  (captured by Mailpit)
    staging       sendgrid   on        no  (validated, not delivered)
    production    sendgrid   off       yes

Resolution order for each setting:
    1. explicit env var (EMAIL_BACKEND / SENDGRID_SANDBOX), else
    2. the APP_ENV default from the table above, else
    3. the ``local`` default (safe: nothing is delivered).

Safety guardrail (fail-closed)
------------------------------
Real delivery — the ``sendgrid`` backend with sandbox OFF — is the only mode
that can email real recipients. It requires a SECOND, explicit opt-in:

    EMAIL_ALLOW_REAL_SEND=true

If that flag is not set, a would-be real send is forced back into SendGrid
*sandbox* mode (validated, never delivered). So no single variable flip can
cause a live blast; you must both select production/sendgrid AND opt in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# APP_ENV -> (backend, sandbox)
_ENV_DEFAULTS: dict[str, tuple[str, bool]] = {
    "local": ("smtp", False),
    "staging": ("sendgrid", True),
    "production": ("sendgrid", False),
}
_FALLBACK_ENV = "local"


def _as_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class EmailConfig:
    app_env: str
    backend: str  # "smtp" | "sendgrid" | "console"
    sandbox: bool
    # True when a real send was requested (sendgrid + sandbox off) but the
    # EMAIL_ALLOW_REAL_SEND opt-in was missing, so we forced sandbox on.
    real_send_blocked: bool = False

    @property
    def delivers(self) -> bool:
        """Whether this config actually delivers to real recipients."""
        if self.backend == "sendgrid":
            return not self.sandbox
        if self.backend == "smtp":
            return True  # delivered to the SMTP host (a catcher locally)
        return False  # console never delivers

    @property
    def mode_label(self) -> str:
        """Human-readable summary for logs / the send-result UI."""
        if self.backend == "console":
            return "console (not sent)"
        if self.backend == "smtp":
            return "smtp (captured by mail catcher)"
        # sendgrid
        if self.sandbox:
            suffix = " — blocked real send, forced sandbox" if self.real_send_blocked else ""
            return f"sendgrid sandbox (validated, not delivered){suffix}"
        return "sendgrid LIVE (really delivered)"


def resolve_email_config(env: dict[str, str] | None = None) -> EmailConfig:
    """Resolve the effective email backend + sandbox flag from the environment."""
    env = env if env is not None else dict(os.environ)

    app_env = env.get("APP_ENV", _FALLBACK_ENV).strip().lower()
    default_backend, default_sandbox = _ENV_DEFAULTS.get(
        app_env, _ENV_DEFAULTS[_FALLBACK_ENV]
    )

    # Explicit override wins over the APP_ENV default.
    backend = (env.get("EMAIL_BACKEND") or default_backend).strip().lower()

    sandbox_override = _as_bool(env.get("SENDGRID_SANDBOX"))
    sandbox = default_sandbox if sandbox_override is None else sandbox_override

    # Guardrail: a real send (sendgrid + sandbox off) needs a second opt-in.
    real_send_blocked = False
    if backend == "sendgrid" and not sandbox:
        allow_real = _as_bool(env.get("EMAIL_ALLOW_REAL_SEND")) or False
        if not allow_real:
            sandbox = True  # fail closed: validate, don't deliver
            real_send_blocked = True

    return EmailConfig(
        app_env=app_env,
        backend=backend,
        sandbox=sandbox,
        real_send_blocked=real_send_blocked,
    )
