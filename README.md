# 🏆 SportsAcademy ERP — Multi-Sport Coaching Academy

A production-grade, security-hardened **Django** ERP that implements the
*Multi-Sport Coaching Academy — Product Requirements Document* in full: four
role experiences (**Admin, Manager, Coach, Parent**) over one shared,
real-time-consistent data model. Mobile / tablet / desktop responsive,
passwordless email-OTP login with rate limiting, and a defence-in-depth
security posture.

> Built to be run today: SQLite + console email out of the box, one command
> to seed a realistic demo academy, and a clean upgrade path to Postgres +
> real SMTP / Razorpay / Twilio for production.

---

## 1. Quick start (5 minutes)

```bash
# 1. create + activate a virtualenv
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 2. install
pip install -r requirements.txt

# 3. environment — optional in dev (sane defaults apply). To customize:
cp .env.example .env        # then edit if you like

# 4. database + demo data
python manage.py migrate
python manage.py seed_demo --reset

# 5. run
python manage.py runserver
```

Open **http://127.0.0.1:8000/** → you'll be sent to the sign-in screen.

### How to sign in (dev)

Login is **passwordless** — you enter an email and receive a 6-digit OTP.
In development the OTP is **printed to the runserver console** *and* shown on
screen (a `[DEV]` banner), so no real mailbox is needed.

| Role    | Email                                   |
| ------- | --------------------------------------- |
| Admin   | `adiseelansri@gmail.com`                |
| Manager | `manager1@demo.local`, `manager2@demo.local` |
| Coach   | `coach1@demo.local` … `coach4@demo.local` |
| Parent  | `parent1@demo.local` … `parent12@demo.local` |

Django admin (`/admin/`): `adiseelansri@gmail.com` / `Champion@Admin1`
*(change this immediately outside a demo).*

> **Tip (Tanglish):** OTP-a paakka runserver terminal-la paaru — `[DEV] Your
> code is XXXXXX` nu print aagum. Adha login screen-la type pannu.

### Creating an admin & managing staff

`seed_demo` already creates the admin account above. For a **fresh** project
without demo data, create the first admin with:

```bash
python manage.py createsuperuser      # email + password; it becomes the Admin
```

That account signs into the **portal** at `/auth/login/` with an email OTP
(like everyone), and into the built-in Django `/admin/` with its password.

**You don't need `/admin/` for day-to-day work** — the Admin portal has its
own white-themed screens to create and assign everything:

- **Branches** → *+ New branch* (name, geo-coordinates, radius, sports)
- **Batches** → open a branch → *Batches* tab → *+ New batch* (sport + schedule)
- **Coaches** → *+ Add coach*, then *Assign batches* (reassign anytime)
- **Managers** → *+ Add manager*, then *Assign branches* (reassign anytime)
- **Parents** are created automatically when you add a student (by email)

Every role signs in the same way (email OTP) and lands on its own dashboard.
The Django `/admin/` remains available as a power-user back office and is also
themed to match (white + branded).

---

## 2. What's inside — PRD coverage

Every section of the spec is implemented:

| PRD area | Where it lives |
| --- | --- |
| Core entities (Academy→Branch→Sport→Batch→Student…) | `apps/academy`, `apps/students` |
| Roles & permission model (scoped access) | `apps/accounts/permissions.py`, `apps/academy/scoping.py` |
| Admin: revenue dashboard, drill-down, branch/coach/manager mgmt, reporting | `apps/portal/views/dashboards.py`, `analytics.py`, `reports.py` |
| Manager: branch-scoped students, fee handling, coach oversight | `apps/portal/views/dashboards.py`, `students.py`, `fees.py` |
| Coach: geo-fenced check-in, attendance, session history | `apps/attendance`, `apps/portal/views/coach.py` |
| Parent: children overview, online fees, attendance, receipts | `apps/portal/views/parent.py`, `fees.py` |
| Real-time "who's running a session where" | `apps/portal/views/common.py` (`live_json`) + polling JS |
| Fee engine (fixed-monthly & package w/ validity, overdue, partial) | `apps/fees/models.py`, `services.py`, `periods.py` |
| Unified payments ledger (online + manual reconciled identically) | `apps/fees/models.py`, `gateways.py` |
| Notifications engine (fee due/overdue, payment, roster, session) multi-channel | `apps/notifications` |
| Audit trail (who did what) | `apps/audit` |
| Multi-tenant-ready data model | `academy` FK on every tenant model; single academy today |

---

## 3. Architecture

One Django project, domain-driven apps:

```
config/            project settings (base/dev/prod), security middleware, urls
apps/
  accounts/        custom User, roles, email-OTP auth, rate limiting, permissions
  academy/         Academy, Branch, Sport, Batch, Manager/Coach assignments, scoping
  students/        Student, Guardian (siblings), Enrollment (multi-sport/branch)
  attendance/      Session, Attendance, geo-fenced check-in service
  fees/            FeePlan, StudentFee, Invoice, Payment ledger, gateways, billing job
  notifications/   Notification + pluggable channel backends + engine
  audit/           AuditLog + auto-capture middleware
  portal/          role dashboards, analytics, SVG charts, live view, reports, CSV
templates/         responsive templates (base shell + per-role)
static/            self-contained CSS design system + vanilla JS (no CDNs)
```

**The four "apps" are role-scoped experiences over shared data.** A single
sign-in routes each user to their portal; every query is filtered by
`apps/academy/scoping.py`, so the same data model safely serves all roles.

---

## 4. Security — defence in depth

This was a hard requirement ("nobody can hack it"). The posture:

**Authentication**
- Passwordless **email OTP** — there is no reusable password to phish or leak.
- OTP codes are **never stored in plaintext** — only an HMAC-SHA256 digest,
  compared in constant time (`hmac.compare_digest`).
- Codes are **single-use** and expire (default 5 min).
- **Rate limiting:** max **5 code requests**, then a **cooldown** wait
  (default 15 min) — exactly as specified. Counters are committed
  independently of request flow so they can't be rolled back by a raised error.
- **Brute-force protection:** max wrong-code attempts per code (default 5),
  after which the code is burned. Every attempt is logged (`LoginEvent`).
- **No user enumeration:** the response is identical whether or not the email
  is registered; the send counter advances either way.

**Authorization (the real ERP boundary)**
- Central `scoping.py` enforces row-level access: Manager → own branches,
  Coach → own batches, Parent → own children, Admin → own academy. This blocks
  IDOR / horizontal privilege escalation. Enforced inside every queryset, not
  just in the UI.

**Transport & headers**
- Strict **Content-Security-Policy** (`script-src 'self'`, no inline JS, no
  CDNs), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  Referrer-Policy, Permissions-Policy, COOP.
- Production: HSTS (1y preload), SSL redirect, `Secure`/`HttpOnly`/`SameSite`
  cookies, session rotation on login, idle timeout.
- `python manage.py check --deploy` passes with **zero issues** under prod
  settings.

**Data & platform**
- Argon2 password hashing (for the `/admin/` staff account).
- CSRF protection on every form; ORM everywhere (no raw SQL → no injection).
- Secrets from environment only (`.env` git-ignored); `DEBUG=False` and a
  strong `SECRET_KEY` are enforced in production (`prod.py` refuses to boot
  otherwise).
- Full **audit trail** of sensitive actions (payments, waivers, roster
  changes, student add/remove).

---

## 5. Feature tour by role

**Admin** — academy-wide revenue (collected / outstanding) for any month or
year (period picker), with trend, by-branch and by-sport charts, a live-sessions view and recent payments; branch,
coach (with live status), and manager management; full financial control;
audit trail; CSV reports.

**Manager** — branch-scoped dashboard, add/manage students, enroll into
batches with a fee plan, fee status + reminders + offline payment recording,
live coach status, reports.

**Coach** — today's batches, **geo-fenced check-in** (browser geolocation vs
branch radius, with a flagged manual fallback), attendance (present/late/
absent) that closes the session, session history.

**Parent** — all children in one account, each child's sports/batches/coach/
schedule, fee status, **pay online**, downloadable receipts, attendance
history, and live "session in progress" visibility.

---

## 6. Going to production

### Database (Postgres)
Set `DATABASE_URL=postgres://user:pass@host:5432/dbname` in the environment.
Install the driver: `pip install "psycopg[binary]"`.

### Settings
Run with `DJANGO_SETTINGS_MODULE=config.settings.prod` and set:
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS`,
`SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`,
`CSRF_COOKIE_SECURE=True`, `SECURE_HSTS_SECONDS=31536000`.

```bash
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```
Static files are served hashed + compressed via WhiteNoise. Works cleanly on
**Railway** and **PythonAnywhere**.

**Uploaded media** (branch cover photos) is stored in `media/` (`MEDIA_ROOT`).
Django serves it only with `DEBUG=True`; in production map the URL `/media/`
to that folder on your web server (PythonAnywhere: *Web → Static files*), or
use object storage.

### Real providers (all optional — safe stubs by default)

| Capability | Default (works now) | Go live |
| --- | --- | --- |
| OTP / notification **email** | console backend (prints) | set `EMAIL_BACKEND=…smtp…` + Gmail App Password in `.env` |
| **Online payments** | `MockGateway` (signed + verified, no real money) | `PAYMENT_GATEWAY_BACKEND=apps.fees.gateways.RazorpayGateway` + `pip install razorpay` + keys |
| **SMS / WhatsApp / Push** | console backends (log the message) | point `NOTIFICATION_CHANNELS` at Twilio/FCM classes + keys |

The service and template layers don't change when you swap a provider — only
the backend class and its keys.

> **Google "Sign in with Google":** email-OTP already delivers to the user's
> Gmail. If you additionally want the Google OAuth button, add
> `django-allauth`, register a Google OAuth client, and wire it alongside the
> OTP flow — the `accounts` app is structured to accept it.

### Recurring billing
`python manage.py run_billing` generates the next period's invoices and flags
overdue fees (firing reminders). Schedule it **daily**, e.g. cron:
```
0 6 * * *  /path/.venv/bin/python /path/manage.py run_billing
```

---

## 7. Testing

```bash
python manage.py test          # 63 tests: OTP rate-limit + brute-force, role scoping, fee engine,
                               # access control, admin dashboard + period picker, CSP-safe templates
python manage.py check --deploy   # security posture (0 issues under prod)
```

---

## 8. Notes & scope

- **Real-time** session tracking uses lightweight polling (a JSON endpoint
  refreshed every few seconds) — honest "near real-time" without extra infra.
  To upgrade to push, drop in Django Channels behind the same `live_json` data.
- The **mock payment gateway is real cryptographically** (HMAC-signed orders,
  verified server-side) — only the money movement is simulated, so the whole
  parent→pay→receipt flow is demoable end to end.
- Multi-academy (multi-tenant) is **schema-ready** (academy FK everywhere)
  though only one academy is in scope, per the PRD.
- **Front-end convention:** the CSP only allows `'self'` for styles and scripts, so
  templates must not use inline `style="…"` or `onclick=` / `onchange=` — browsers
  silently ignore them. Use the helper classes at the bottom of `static/css/app.css`
  and the `data-*` hooks in `static/js/app.js`; a unit test enforces this.

Built as a master-level reference implementation. Enjoy. 🏆
