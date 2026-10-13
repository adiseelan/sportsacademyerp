# Changelog

## Release 22 — 2026-10-11

### Branch page
- **＋ New batch** (Batches tab) and **＋ Add student** (Students tab) are now primary buttons: blue background with white text, so the main action on each tab stands out.
- 1 new test. Total: 63.

## Release 21 — 2026-10-11

### Branch page header
- The exposed **✏️ Edit** button is replaced by a **⋮ (more_vert)** menu at the top right. *Edit branch* (details, photo & sports) is inside it.
- The menu uses the same dropdown as the dashboard: it closes on an outside click or Esc. The ⋮ is 40 px with a grey icon, like the bell.
- On phones the ⋮ stays on the same row as the branch name. The header no longer wraps the button onto its own line.
- 1 new test. Total: 62.

## Release 20 — 2026-10-11

### Branch page — Fees tab: one table
- The Collected / Outstanding tiles no longer switch between two lists. They are plain totals now.
- **One table** below them lists both who paid and who hasn't. Columns: student, what for, date, status, amount, and an action.
  - **Paid rows** are the payments received in the period: green *Paid* badge, amount, and a *Receipt* button.
  - **Unpaid rows** are invoices still open at the end of the period, arrears included: *Due* date, Overdue / Partially paid / Due badge, balance, and an *Open* button.
  - Rows are sorted A–Z by student, so a student's payment and remaining balance sit together.
- A small **All · Paid · Unpaid** filter with counts sits at the right of the table header (`?show=paid|unpaid`; All is the default). The footer shows *Total collected* and/or *Total outstanding* to match the filter, and these always equal the tiles.
- The period picker keeps the filter, and the filter keeps the period. Old `?view=collected|outstanding` links still work.
- On phones the filter goes full width and table rows stay on one line (the table scrolls sideways).

### Sidebar
- **Batches** is removed from the admin sidebar. Batches live inside each branch (branch page → *Batches* tab).
- The batch new / edit pages highlight *Branches*. Their *← Back* and *Cancel* links lead to that branch's Batches tab, and so does saving. The `/app/admin/batches/` URL still works.

- 2 new tests; the Fees tab tests were rewritten for the single table. Total: 61.

## Release 19 — 2026-10-07

### Branch page — Fees tab
- Only two tiles now: **Collected** and **Outstanding** (the Students tile is gone).
- The tiles are clickable and switch the list below:
  - **Collected → who paid:** every payment received at this branch in the chosen period — date, student, what it was for, method, receipt link, amount — with a *Total collected* row.
  - **Outstanding → who hasn't paid:** every unpaid / part-paid invoice at this branch due by the end of the period (arrears included) — student, what for, invoice, due date, status, paid, balance, *Open* — with a *Total outstanding* row.
- The list totals always equal the tile amounts (both come from the same queries: `analytics.period_payments()` / `period_unsettled()`).
- The period picker keeps both the Fees tab and the chosen list (`?tab=fees&view=outstanding&period=2026-10`).
- Money columns in tables are right-aligned.
- 2 new tests. Total: 59.

## Release 18 — 2026-10-07

### Branch page — Fees tab
- New **Fees** tab after *Students* with the dashboard's three tiles — **Collected**, **Outstanding**, **Students** — calculated for **this branch only** (its invoices, payments, enrolled students and active batches). The three branches' figures add up to the dashboard totals.
- Same Monthly / Yearly period picker as the dashboard (default: current month); choosing a period keeps you on the Fees tab (`?tab=fees&period=2026-10`).
- The period picker is now a shared partial (`portal/admin/_period_dropdown.html`); `analytics.period_summary()` and `first_payment_date()` accept an optional `branch`.
- Tabs fit on phones (smaller gaps), and the picker goes full width there.
- 2 new tests. Total: 57.

## Release 17 — 2026-10-06

### Branch page
- New **Students** tab next to *Batches*: everyone currently enrolled at the branch (withdrawn enrollments are left out) with age, their sport · batch here (paused ones are marked), status, and **Open** to the student's page. The tab shows the count; **＋ Add student** is in the card header.
- 1 new test. Total: 55.

## Release 16 — 2026-10-06

### Branches
- A branch's page now shows **only that branch, full width** — the list of other branches on the left is gone. Use **← All branches** to go back to the card grid and open another branch.
- The status filter menu stays on screen on phones.

## Release 15 — 2026-10-06

### Branches — photo-card overview
- Clicking **Branches** now opens a card grid: a full-width search box (filters as you type), a status filter (All / Active / Inactive) and **＋ New branch**, then one card per branch with its cover image, name, status and address.
- Clicking a card opens that branch's own page (`/app/admin/branches/<id>/`) — the list + details design from Release 14, with an "← All branches" link. Old `?branch=<id>` links redirect there.
- **Cover photos:** branches can now have a photo (Edit branch → *Cover photo*; JPG / PNG / WebP up to 5 MB, file names are randomised, replacing or removing a photo deletes the old file). Branches without a photo get a coloured court-style cover with their sports' icons.
- New model field `Branch.photo` (migration `academy/0003_branch_photo`) — run `python manage.py migrate`.
- New dependency: **Pillow** (in `requirements.txt`) — run `pip install -r requirements.txt`.
- Uploaded files live in `media/`. Django serves them in DEBUG; in production map `/media/` to that folder (see `DEPLOY_PYTHONANYWHERE.md`).
- 4 new tests (grid, redirects, photo upload / replace / validation). Total: 54.

## Release 14 — 2026-10-04

### Branches page — new master–detail design
- **Left pane:** search box (filters as you type; Enter searches on the server), status filter menu (All / Active / Inactive), **＋ New branch**, and the branch list (icon, name, address, status). The selected branch is highlighted.
- **Right pane:** the selected branch with a header (name, status, address, **Edit**) and two tabs:
  - **Overview:** *Basic Information* (name, address, geo-fence, phone | status, code, created on, last updated), *Sports Offered* chips with **＋ Add sport**, and *Managers* with **＋ Add manager** / *Change branches*.
  - **Batches:** every batch at the branch (sport, schedule, coaches, seats, status, Edit) with **＋ New batch** (pre-selects this branch).
- "Last updated" comes from the audit trail (latest branch add/edit), so no migration was needed.
- Creating or editing a branch returns to that branch on this page.
- On phones the list and the details stack.
- 5 new tests. Total: 50.

## Release 13 — 2026-10-04

### Live Sessions page
- Back to the approved look: rows about 59px tall again (were about 72px) and no vertical divider lines between columns.
- The ⋮ (more_vert) actions button on every row stays.

## Release 12 — 2026-10-04

### Live Sessions page
- Every row now ends with a **⋮ (more_vert)** button that opens a small actions menu for that session:
  - Admin: *View attendance*, *Edit batch*, *Call coach* (if a phone is on file), *Email coach*.
  - Manager: *Call coach*, *Email coach* (the other two pages are admin-only).
- The menu floats above the table, so it is never cut off by the scrolling box; it flips upward near the bottom, stays attached while the table scrolls, and closes on outside click / Esc. Auto-refresh pauses while a menu is open.
- The ⋮ column stays pinned to the right edge on phones when the table scrolls sideways.
- `live/data/` JSON now includes `id` and per-row `actions`.
- 2 new tests. Total: 45.

## Release 10 — 2026-10-04

### Live Sessions page
- "Updated hh:mm:ss" is back at the top left and the "N live" pill at the top right, where they were originally (without the old heading), above the card.
- Only the auto-refresh note stays below the card.
- Taller table rows (about 72px each, was about 48px) and vertical divider lines between the columns.
- The table's scrollbar is styled so it stays visible when the list is longer than the box (macOS otherwise hides it).

## Release 9 — 2026-10-04

### Live Sessions page
- Removed the "Who's running a session" heading block from the top.
- The sessions card now always fills the screen below the top bar and keeps that size whether 0, 1 or 50 coaches are live; long lists scroll inside it with the header row pinned. Column widths are fixed so they don't shift as data changes.
- "Updated hh:mm:ss" and the "N live" count moved to a footer line under the card.
- `base.html` gained an optional `{% block content_class %}` hook for full-height pages.
- 1 new test. Total: 43.

## Release 8 — 2026-10-04

### Sidebar & top bar (all roles)
- Removed *Notifications* and *Profile* from the sidebar (and the empty *Account* group). Notifications open from the bell at the top right.
- *My profile* now opens by clicking the name / role chip at the bottom of the sidebar (e.g. "Adi · Admin"); it is highlighted while on the profile page.
- The bell is a grey outline icon (turns brand colour on the Notifications page); the red unread count stays.
- 1 new test. Total: 42.

## Release 7 — 2026-10-04

### Notifications page
- Removed the big "Notifications" page heading (the top bar already says it); *Mark all read* stays, right-aligned.
- "Open →" replaced by a grey **✕** on every row that dismisses (deletes) that notification. It works in place without a page reload and updates the unread badges; without JS it falls back to a normal POST.
- To open a notification's page, click its title (it is marked read, as before).
- New endpoint `notifications/<id>/dismiss/` (POST only, own notifications only).
- 4 new tests. Total: 41.

## Release 6 — 2026-10-04

- Period picker no longer lists empty past months/years: the *Monthly* list runs from the current month back to the month of the first recorded payment (the *Yearly* list likewise). With no payments yet, only the current month/year is shown.
- 1 new test. Total: 37.

## Release 5 — 2026-10-04

### Admin dashboard
- **Period picker** in the header (where *Export reports* was): a button showing e.g. *Oct 2026 · 01 Oct – 31 Oct 2026* opens a list with **Monthly / Yearly** tabs. Default is the current month; the choice is kept in the URL (`?period=2026-10`, `?period=2026`).
- Everything money-related follows the chosen period: *Collected* (payments received in the period), *Outstanding* (still unpaid on invoices due by the period's last day, arrears included), the donut, *By branch*, *Revenue by sport* and *Recent payments*. *Revenue trend* shows the 6 months up to the chosen month, or Jan–Dec for a year. *Students* stays the live total, with "+N new" joined in the period. *Live sessions* stays real-time.
- **⋮ menu** next to the picker: *Revenue CSV* for the chosen period, and *Export reports* (all CSV reports).
- *Live sessions* card: the link is back as **View →** (it was "Open live view →").
- `reports/revenue.csv` accepts the same optional `?period=` filter.
- Built with `<details>` + CSS, so the picker works under the strict CSP; `app.js` only adds close-on-outside-click / Esc.

### Tests
- 11 new tests (period parsing, period-scoped totals, CSV filter, picker and View link). Total: 36.

## Release 4 — 2026-10-04

### Admin dashboard
- Removed the filter bar (From / To / Branch / Sport / *Apply filters*). The dashboard is now a fixed, academy-wide view.
- Headline tiles are **Collected · Outstanding · Students**. The *Overdue* tile is gone (overdue invoices are still available under *Fees → Overdue*).
- The *Live sessions* card is view-only: the "Open live view →" link was removed (the full page is still in the sidebar under *Live Sessions*).

### Layout & spacing
- New spacing scale in `static/css/app.css` (`--gap`, `--pad-x`, `--pad-y`): roomier page, card, tile and table padding, consistent gaps between sections, slightly tighter values on phones.
- Fixed spacing that was silently not applied: the Content-Security-Policy (`style-src 'self'`) blocks inline `style="…"` attributes, so ~100 one-off margins, paddings and max-widths in the templates never took effect. They now live as helper classes at the bottom of `app.css`. The CSP itself is unchanged.
- Notification bell badge is pinned to the corner of the button; unread dots use the brand colour; list rows have dividers.

### Fixes
- *Audit Trail* action filter and the receipt *Print / Save PDF* button now work. They relied on inline `onchange` / `onclick`, which the CSP blocks; they are wired through `data-autosubmit` / `data-print` in `static/js/app.js`.

### Tests
- 5 new tests: admin dashboard content, legacy filter query-string is ignored, and a guard that fails if a template adds inline `style=` / `on*=`. Total: 25.
