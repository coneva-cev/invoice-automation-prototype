# SendGrid email verification runbook

How to verify that emails are sent correctly via SendGrid **before** any real
customer receives mail — driven from the UI, with server-side guardrails.

## The model

`EMAIL_MODE` (env) is the single authority for whether a send can reach a real
customer. It controls which **destinations** the Send step offers; the operator
picks one per send.

| `EMAIL_MODE` | Destinations offered | Recipients |
| --- | --- | --- |
| **test** | Mailpit · SendGrid sandbox · SendGrid → coneva | **Always replaced** with a domain-allowed (`coneva.com`) address chosen in the UI. No email can reach a customer. |
| **live** | SendGrid sandbox · SendGrid live | Sandbox delivers nothing; **live** delivers to the real recipients from the mapping. |

If `EMAIL_MODE` is unset it is derived from `APP_ENV` (production → live, else
test), so a fresh environment is safe (test) by default. Set it explicitly.

**All safety is enforced server-side** in `resolve_send_plan` (the single
authority), at the one point the outbound email is built. The UI only chooses
among the destinations the mode allows and can never widen them. In test mode a
non-`coneva.com` (or missing) replacement address makes the send fail-closed
(HTTP 400, nothing sent).

There is no `EMAIL_ALLOW_REAL_SEND` any more — `EMAIL_MODE=live` + the operator
picking the **SendGrid live** destination (behind a destructive confirmation)
are the gates.

## Env for verification

```bash
# backend/.env  (test instance)
EMAIL_MODE=test
SENDGRID_API_KEY=SG.xxxxx                 # production key, reused for testing
EMAIL_FROM="coneva <noreply@coneva.com>"
EMAIL_TEST_RECIPIENTS=you@coneva.com      # default replacement (editable in UI)
# EMAIL_TEST_ALLOWED_DOMAINS=coneva.com   # default; where replacement may point
SMTP_HOST=localhost                        # for the Mailpit destination
SMTP_PORT=1025
```

Restart the backend after changing `.env`.

## Verification ladder (all from the Send step)

The Send step shows a **TEST MODE** banner and a **Send destination** selector.

1. **Mailpit** — `make mailpit`, pick *Mailpit*, keep the coneva address, send.
   Nothing leaves the machine. Open http://localhost:8025 and check subject,
   body copy + links, and the attached PDFs. Recipients are the coneva test
   address (the intended recipient is shown in the subject / a banner in the
   email).

2. **SendGrid sandbox** — pick *SendGrid sandbox*, send. This makes the real
   SendGrid API call with your key and payload; SendGrid validates and returns
   202 but **delivers nothing**. Confirms auth + payload. A 401/403 means the
   key/permissions are wrong.

3. **SendGrid → coneva** — pick *SendGrid → coneva address*, enter your
   `@coneva.com` address, send. This is a **real** SendGrid delivery, forced to
   your inbox. Verify HTML rendering, attachments, and deliverability/DKIM as an
   actual recipient. A non-coneva address is refused server-side.

Once all three look correct, switch the instance to live for the real send.

## Real customer send (live instance)

```bash
# backend/.env  (live instance)
EMAIL_MODE=live
SENDGRID_API_KEY=SG.xxxxx
EMAIL_FROM="coneva <noreply@coneva.com>"
```

On the Send step the mode badge reads **LIVE MODE** and the destinations are
*SendGrid sandbox* and *SendGrid live*. Do a **sandbox** send first (dry run),
then pick **SendGrid live** — the button turns red ("Send N to customers") and a
confirmation ("Send to real customers? … cannot be undone") must be confirmed.
The `billing@coneva.com` BCC is applied to every real email.

## Safety checklist before a real customer send

- [ ] Mailpit: body / attachments / links verified.
- [ ] SendGrid sandbox returned success (202).
- [ ] SendGrid → coneva: email received in your inbox, rendered, attachments
      open, not marked spam.
- [ ] Instance is on `EMAIL_MODE=live` intentionally.
- [ ] `EMAIL_FROM` is a verified SendGrid sender.
- [ ] The recipient mapping (xlsx) has the correct customer addresses.
- [ ] Drafts and the selected set reviewed on the Send step.

## Reference: variables

| Variable | Effect |
| --- | --- |
| `EMAIL_MODE` | `test` \| `live` — the single delivery-safety authority |
| `EMAIL_TEST_RECIPIENTS` | Default (editable) replacement address in test mode |
| `EMAIL_TEST_ALLOWED_DOMAINS` | Domains a replacement address may use (default `coneva.com`) |
| `SENDGRID_API_KEY` | SendGrid API key |
| `EMAIL_FROM` | Sender address (must be a verified SendGrid sender) |
| `EMAIL_BCC` | BCC on every real email (default `billing@coneva.com`) |
| `SMTP_HOST` / `SMTP_PORT` | Mailpit destination target |
