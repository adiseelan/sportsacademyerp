# Deploy to PythonAnywhere — team testing (on-screen OTP)

A step-by-step to get the ERP live at `https://<username>.pythonanywhere.com/`
so your team can test it. Tuned for **on-screen OTP codes** (no email setup
needed): a tester enters their email, and the code appears on the screen.

> ⚠️ This is a **testing** setup. `OTP_SHOW_ON_SCREEN` means anyone who knows a
> registered email can sign in — fine for a trusted test team with throwaway
> data, NOT for a real launch. For production, turn the flag off and wire real
> email (see README §6).

---

## 0. Before you start

- **Free tier gives one web app per account.** Your portfolio already uses
  `adiseelan.pythonanywhere.com`, so either use your **`qrservice`** account, a
  fresh free account, or the $5 “Hacker” plan to run a second app.
- Push this project to GitHub first (easiest to pull onto PythonAnywhere).
  Free-tier PythonAnywhere can reach `github.com` fine.

---

## 1. Open a Bash console (PythonAnywhere → Consoles → Bash)

```bash
git clone https://github.com/<you>/sportsacademyerp.git
cd sportsacademyerp

mkvirtualenv --python=/usr/bin/python3.10 sportsacademyerp
pip install -r requirements.txt          # core only — no gunicorn/psycopg needed here
```

## 2. Create the `.env` file (same folder)

Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Then `nano .env` and paste (replace USERNAME + the key):
```
DJANGO_SECRET_KEY=<paste-the-generated-key>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=USERNAME.pythonanywhere.com
DJANGO_SETTINGS_MODULE=config.settings.dev
DATABASE_URL=
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
OTP_SHOW_ON_SCREEN=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```
(`DEBUG=False` keeps error pages private; `OTP_SHOW_ON_SCREEN=True` still shows
the code on screen. SQLite is used since `DATABASE_URL` is blank — perfect for
testing.)

## 3. Set up the database + demo data

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_demo            # ready-made accounts across all roles
```

## 4. Web tab → Add a new web app → **Manual configuration** → Python 3.10

Then set:
- **Source code:** `/home/USERNAME/sportsacademyerp`
- **Working directory:** `/home/USERNAME/sportsacademyerp`
- **Virtualenv:** `/home/USERNAME/.virtualenvs/sportsacademyerp`

**WSGI configuration file** (click it, delete everything, paste):
```python
import os, sys

path = "/home/USERNAME/sportsacademyerp"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.dev"

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```
(The `.env` file is picked up automatically by the settings.)

**Static files** (Web tab → Static files):
| URL | Directory |
|-----|-----------|
| `/static/` | `/home/USERNAME/sportsacademyerp/staticfiles` |

## 5. Reload

Hit the big green **Reload** button. Open
`https://USERNAME.pythonanywhere.com/` → you'll land on the sign-in page.

---

## 6. How your team logs in

Give testers any seeded account — they enter the email, and the 6-digit code
shows on screen (yellow banner). No inbox needed.

| Role | Email |
|------|-------|
| Admin | `adiseelansri@gmail.com` |
| Manager | `manager1@demo.local`, `manager2@demo.local` |
| Coach | `coach1@demo.local` … `coach4@demo.local` |
| Parent | `parent1@demo.local` … `parent12@demo.local` |

To add your real teammates: log in as Admin → **Managers / Coaches → Add**, or
**Students → Add** (auto-creates a Parent). They then log in with that email
(code on screen).

---

## 7. Updating the deployed app later

```bash
workon sportsacademyerp
cd ~/sportsacademyerp && git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```
Then **Reload** on the Web tab.

## Troubleshooting
- **DisallowedHost / 400** → the domain isn't in `DJANGO_ALLOWED_HOSTS`. Fix
  `.env`, reload.
- **CSS missing / unstyled** → re-run `collectstatic` and check the static
  mapping path, then reload.
- **CSRF 403 on forms** → confirm `DJANGO_ALLOWED_HOSTS` has your exact
  `USERNAME.pythonanywhere.com` (the app auto-trusts that https origin).
- **Server error page is blank** → open the **Error log** (Web tab) — with
  `DEBUG=False` details go there, not to the browser.
