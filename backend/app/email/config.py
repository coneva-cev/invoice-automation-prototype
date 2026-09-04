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

Delivery safety
---------------
Whether a send can reach a real customer is NOT decided here. It is decided by
``EMAIL_MODE`` (test | live) and the per-send destination, validated centrally
in :func:`resolve_send_plan`. See that function and the send router.
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
        """Human-readable summary for logs."""
        if self.backend == "console":
            return "console (not sent)"
        if self.backend == "smtp":
            return "smtp (captured by mail catcher)"
        if self.sandbox:
            return "sendgrid sandbox (validated, not delivered)"
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

    return EmailConfig(
        app_env=app_env,
        backend=backend,
        sandbox=sandbox,
    )


# Every outgoing email is blind-copied to this address (billing archive).
# Overridable via EMAIL_BCC; set to empty to disable.
_DEFAULT_BCC = "billing@coneva.com"


def resolve_bcc(env: dict[str, str] | None = None) -> list[str]:
    """Return the BCC recipient(s) applied to every outgoing email.

    Defaults to ``billing@coneva.com``. Set ``EMAIL_BCC`` to override with a
    comma-separated list, or to an empty string to disable the BCC entirely.
    """
    env = env if env is not None else dict(os.environ)
    raw = env.get("EMAIL_BCC", _DEFAULT_BCC)
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


# ---------------------------------------------------------------------------
# App mode + send destinations (the authoritative delivery-safety model)
# ---------------------------------------------------------------------------
# ``EMAIL_MODE`` (test | live) controls which destinations a send may target.
# All enforcement happens server-side in resolve_send_plan; the UI only chooses
# among the destinations the mode allows and can never widen them.
DEST_MAILPIT = "mailpit"
DEST_SENDGRID_SANDBOX = "sendgrid_sandbox"
DEST_SENDGRID_CONEVA = "sendgrid_coneva"  # test-mode: deliver to a coneva addr
DEST_SENDGRID_LIVE = "sendgrid_live"  # live-mode: deliver to real customers

# Which destinations each app mode permits (order = UI display order).
_DESTINATIONS_BY_MODE: dict[str, tuple[str, ...]] = {
    "test": (DEST_MAILPIT, DEST_SENDGRID_SANDBOX, DEST_SENDGRID_CONEVA),
    "live": (DEST_SENDGRID_SANDBOX, DEST_SENDGRID_LIVE),
}

_DEFAULT_ALLOWED_TEST_DOMAINS = ("coneva.com",)


def resolve_app_mode(env: dict[str, str] | None = None) -> str:
    """Return the authoritative app email mode: ``"test"`` or ``"live"``.

    ``EMAIL_MODE`` wins when set to test/live. Otherwise it is derived from
    ``APP_ENV`` (production => live; anything else => test) so a fresh
    environment is safe (test) by default.
    """
    env = env if env is not None else dict(os.environ)
    explicit = (env.get("EMAIL_MODE") or "").strip().lower()
    if explicit in ("test", "live"):
        return explicit
    app_env = (env.get("APP_ENV") or _FALLBACK_ENV).strip().lower()
    return "live" if app_env == "production" else "test"


def resolve_allowed_test_domains(env: dict[str, str] | None = None) -> list[str]:
    """Domains a test-mode replacement address must belong to.

    Configurable via ``EMAIL_TEST_ALLOWED_DOMAINS`` (comma-separated); defaults
    to ``coneva.com``. An empty/invalid override falls back to the default so
    the guardrail can never be silently disabled.
    """
    env = env if env is not None else dict(os.environ)
    raw = env.get("EMAIL_TEST_ALLOWED_DOMAINS", "")
    domains = [d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()]
    return domains or list(_DEFAULT_ALLOWED_TEST_DOMAINS)


def resolve_test_default_recipient(env: dict[str, str] | None = None) -> str | None:
    """The default replacement address pre-filled in the UI (editable).

    Taken from the first entry of ``EMAIL_TEST_RECIPIENTS`` if present.
    """
    env = env if env is not None else dict(os.environ)
    raw = env.get("EMAIL_TEST_RECIPIENTS", "")
    entries = [a.strip() for a in raw.split(",") if a.strip()]
    return entries[0] if entries else None


def allowed_destinations(mode: str) -> list[str]:
    """Destinations permitted for the given app mode."""
    return list(_DESTINATIONS_BY_MODE.get(mode, ()))


def is_email_domain_allowed(addr: str, allowed_domains: list[str]) -> bool:
    """True when ``addr`` is a simple address in one of ``allowed_domains``.

    Deliberately strict and simple: exactly one ``@``, a non-empty local part,
    and the domain (case-insensitive) is in ``allowed_domains``.
    """
    if not addr or addr.count("@") != 1:
        return False
    local, _, domain = addr.partition("@")
    if not local.strip():
        return False
    return domain.strip().lower() in {d.lower() for d in allowed_domains}


@dataclass(frozen=True)
class SendPlan:
    """A validated, safe plan for one send request.

    Produced by :func:`resolve_send_plan`, the SINGLE authority that turns
    (app mode + requested destination + requested replacement address) into a
    decision. If ``ok`` is false the send MUST be refused with ``error`` and
    nothing may be sent. When ``ok`` is true:

      * ``kind``          — the validated destination.
      * ``backend``       — "smtp" | "sendgrid".
      * ``sandbox``       — SendGrid sandbox flag for this send.
      * ``replace_to``    — when set, EVERY recipient (To/Cc/Bcc) must be
                            replaced with this single address. When ``None`` the
                            original recipients are used (live real send).
      * ``delivers_real`` — true only when this send can reach real customers.
    """

    ok: bool
    kind: str
    backend: str
    sandbox: bool
    replace_to: str | None
    delivers_real: bool
    error: str | None = None


def resolve_send_plan(
    kind: str | None,
    replace_to: str | None,
    env: dict[str, str] | None = None,
) -> SendPlan:
    """Validate a requested destination against the app mode and guardrails.

    The one place that decides whether/how a send may proceed. Fail-closed: any
    invalid combination yields ``ok=False`` and the caller must refuse to send.
    It NEVER lets a test-mode send reach a non-allowed address, and NEVER lets a
    live-customer destination run outside live mode.
    """
    env = env if env is not None else dict(os.environ)
    mode = resolve_app_mode(env)
    allowed = allowed_destinations(mode)

    def fail(msg: str) -> SendPlan:
        return SendPlan(
            ok=False,
            kind=kind or "",
            backend="",
            sandbox=True,
            replace_to=None,
            delivers_real=False,
            error=msg,
        )

    if not kind:
        return fail("No send destination selected.")
    if kind not in allowed:
        return fail(
            f"Destination '{kind}' is not permitted in '{mode}' mode "
            f"(allowed: {', '.join(allowed)})."
        )

    # Recipient replacement: in TEST mode every destination diverts all mail to
    # a single domain-checked address; in LIVE mode nothing is replaced.
    resolved_replace: str | None = None
    if mode == "test":
        addr = (replace_to or "").strip()
        if not addr:
            return fail(
                "A replacement recipient address is required for this "
                "destination."
            )
        allowed_domains = resolve_allowed_test_domains(env)
        if not is_email_domain_allowed(addr, allowed_domains):
            return fail(
                f"Replacement recipient '{addr}' must be an address in: "
                f"{', '.join(allowed_domains)}."
            )
        resolved_replace = addr

    # Transport + sandbox per destination.
    if kind == DEST_MAILPIT:
        backend, sandbox = "smtp", False
    elif kind == DEST_SENDGRID_SANDBOX:
        backend, sandbox = "sendgrid", True
    elif kind == DEST_SENDGRID_CONEVA:
        backend, sandbox = "sendgrid", False  # delivers, but only to a coneva addr
    elif kind == DEST_SENDGRID_LIVE:
        backend, sandbox = "sendgrid", False
    else:  # pragma: no cover - guarded by the allow-list above
        return fail(f"Unknown destination '{kind}'.")

    return SendPlan(
        ok=True,
        kind=kind,
        backend=backend,
        sandbox=sandbox,
        replace_to=resolved_replace,
        delivers_real=(kind == DEST_SENDGRID_LIVE),
    )


def build_send_mode_view(env: dict[str, str] | None = None) -> dict:
    """Shape the email-mode view the UI needs to render the Send step.

    Single source of truth for what the frontend shows: the app mode, the
    destinations it may offer, the default (editable) replacement address, the
    allowed test domains, and the billing BCC.
    """
    env = env if env is not None else dict(os.environ)
    mode = resolve_app_mode(env)
    return {
        "app_mode": mode,
        "destinations": allowed_destinations(mode),
        "test_default_recipient": resolve_test_default_recipient(env),
        "test_allowed_domains": resolve_allowed_test_domains(env),
        "bcc": resolve_bcc(env),
    }
