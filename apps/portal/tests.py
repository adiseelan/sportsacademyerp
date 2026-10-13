import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.academy.models import Batch, Branch, CoachAssignment, ManagerAssignment, Sport
from apps.academy.scoping import accessible_students
from apps.accounts.models import Role, User
from apps.fees import services as fee_services
from apps.fees.models import FeePlan, InvoiceStatus, Payment, PaymentMethod, Period, PlanType
from apps.portal import periods
from apps.students.models import Enrollment, Guardian, Student


class BaseData(TestCase):
    def setUp(self):
        from apps.academy.models import Academy

        self.ac = Academy.objects.create(name="A", slug="a")
        self.admin = User.objects.create_user(email="admin@a.com", full_name="Admin", role=Role.ADMIN, academy=self.ac)
        self.b1 = Branch.objects.create(academy=self.ac, name="B1")
        self.b2 = Branch.objects.create(academy=self.ac, name="B2")
        self.cricket = Sport.objects.create(academy=self.ac, name="Cricket")
        self.batch1 = Batch.objects.create(branch=self.b1, sport=self.cricket, name="Batch1")
        self.batch2 = Batch.objects.create(branch=self.b2, sport=self.cricket, name="Batch2")

        self.mgr = User.objects.create_user(email="m@a.com", full_name="Mgr", role=Role.MANAGER, academy=self.ac)
        ManagerAssignment.objects.create(manager=self.mgr, branch=self.b1)

        self.coach = User.objects.create_user(email="c@a.com", full_name="Coach", role=Role.COACH, academy=self.ac)
        CoachAssignment.objects.create(coach=self.coach, batch=self.batch1)

        self.p1 = User.objects.create_user(email="p1@a.com", full_name="P1", role=Role.PARENT, academy=self.ac)
        self.p2 = User.objects.create_user(email="p2@a.com", full_name="P2", role=Role.PARENT, academy=self.ac)

        self.s1 = Student.objects.create(academy=self.ac, full_name="S1")
        self.s2 = Student.objects.create(academy=self.ac, full_name="S2")
        Guardian.objects.create(parent=self.p1, student=self.s1, is_primary=True)
        Guardian.objects.create(parent=self.p2, student=self.s2, is_primary=True)
        Enrollment.objects.create(student=self.s1, batch=self.batch1, sport=self.cricket, branch=self.b1)
        Enrollment.objects.create(student=self.s2, batch=self.batch2, sport=self.cricket, branch=self.b2)


class ScopingTests(BaseData):
    def test_admin_sees_all_students(self):
        ids = set(accessible_students(self.admin).values_list("id", flat=True))
        self.assertEqual(ids, {self.s1.id, self.s2.id})

    def test_manager_sees_only_own_branch_students(self):
        ids = set(accessible_students(self.mgr).values_list("id", flat=True))
        self.assertEqual(ids, {self.s1.id})

    def test_coach_sees_only_own_batch_students(self):
        ids = set(accessible_students(self.coach).values_list("id", flat=True))
        self.assertEqual(ids, {self.s1.id})

    def test_parent_sees_only_own_child(self):
        ids = set(accessible_students(self.p1).values_list("id", flat=True))
        self.assertEqual(ids, {self.s1.id})
        self.assertNotIn(self.s2.id, ids)


class FeeEngineTests(BaseData):
    def _plan(self):
        return FeePlan.objects.create(
            academy=self.ac, name="Monthly", plan_type=PlanType.FIXED_MONTHLY,
            period=Period.MONTHLY, amount=Decimal("1000"),
        )

    def test_assign_creates_due_invoice(self):
        fee, invoice = fee_services.assign_fee(self.s1, self.cricket, self._plan(), actor=self.admin)
        self.assertEqual(invoice.status, InvoiceStatus.DUE)
        self.assertEqual(invoice.balance, Decimal("1000.00"))
        self.assertEqual(invoice.branch_id, self.b1.id)  # attributed to enrollment branch

    def test_full_payment_marks_paid(self):
        _, invoice = fee_services.assign_fee(self.s1, self.cricket, self._plan(), actor=self.admin)
        fee_services.record_manual_payment(invoice, Decimal("1000"), PaymentMethod.CASH, self.admin)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        self.assertEqual(invoice.balance, Decimal("0.00"))

    def test_partial_payment_marks_partial(self):
        _, invoice = fee_services.assign_fee(self.s1, self.cricket, self._plan(), actor=self.admin)
        fee_services.record_manual_payment(invoice, Decimal("400"), PaymentMethod.UPI, self.admin)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PARTIAL)
        self.assertEqual(invoice.balance, Decimal("600.00"))

    def test_overdue_detection(self):
        _, invoice = fee_services.assign_fee(self.s1, self.cricket, self._plan(), actor=self.admin)
        invoice.due_date = timezone.localdate() - timedelta(days=5)
        invoice.save(update_fields=["due_date"])
        invoice.recompute()
        self.assertEqual(invoice.status, InvoiceStatus.OVERDUE)


class AccessControlTests(BaseData):
    def test_parent_blocked_from_admin_dashboard(self):
        self.client.force_login(self.p1)
        self.assertEqual(self.client.get("/app/admin/").status_code, 403)

    def test_parent_can_reach_parent_home(self):
        self.client.force_login(self.p1)
        self.assertEqual(self.client.get("/app/parent/").status_code, 200)

    def test_manager_reaches_dashboard(self):
        self.client.force_login(self.mgr)
        self.assertEqual(self.client.get("/app/manager/").status_code, 200)

    def test_parent_cannot_open_other_familys_student(self):
        self.client.force_login(self.p1)
        # s2 belongs to p2; parent has no student route, but staff detail must 404 for them anyway
        self.assertIn(self.client.get(f"/app/students/{self.s2.id}/").status_code, (403, 404))


class AdminDashboardTests(BaseData):
    """The admin dashboard is a fixed, academy-wide view (no filter bar)."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        res = self.client.get("/app/admin/")
        self.assertEqual(res.status_code, 200)
        self.html = res.content.decode()

    def test_filter_bar_is_gone(self):
        for needle in ("Apply filters", 'name="from"', 'name="to"', 'name="branch"', 'name="sport"'):
            self.assertNotIn(needle, self.html)

    def test_headline_tiles_are_collected_outstanding_students(self):
        for label in ("Collected", "Outstanding", "Students"):
            self.assertIn(f'<div class="kpi-label">{label}</div>', self.html)
        self.assertNotIn("Overdue", self.html)

    def test_live_sessions_card_links_with_view_only(self):
        self.assertIn("Live sessions", self.html)
        self.assertNotIn("Open live view", self.html)
        self.assertIn('<a class="small" href="/app/live/">View →</a>', self.html)

    def test_period_picker_replaces_export_button(self):
        today = timezone.localdate()
        self.assertIn(f"<b>{today:%b %Y}</b>", self.html)  # e.g. "Oct 2026"
        self.assertIn("Monthly", self.html)
        self.assertIn("Yearly", self.html)
        # "Export reports" now lives in the ⋮ menu next to the picker
        self.assertIn('href="/app/reports/"', self.html)
        self.assertIn(f'href="/app/reports/revenue.csv?period={today:%Y-%m}"', self.html)

    def test_legacy_filter_query_string_is_ignored(self):
        plan = FeePlan.objects.create(
            academy=self.ac, name="Monthly", plan_type=PlanType.FIXED_MONTHLY,
            period=Period.MONTHLY, amount=Decimal("1000"),
        )
        for student in (self.s1, self.s2):  # one payment at each branch
            _, invoice = fee_services.assign_fee(student, self.cricket, plan, actor=self.admin)
            fee_services.record_manual_payment(invoice, Decimal("1000"), PaymentMethod.CASH, self.admin)

        res = self.client.get(f"/app/admin/?branch={self.b1.id}&from=2020-01-01&to=2020-01-02")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["summary"]["collected"], Decimal("2000.00"))


class CspSafeTemplateTests(SimpleTestCase):
    """The CSP only allows 'self' for styles and scripts, so browsers silently drop inline
    style="" attributes and on*="" handlers. Use the helper classes in static/css/app.css
    (and data-* hooks in static/js/app.js) instead."""

    def test_templates_have_no_inline_style_or_event_handlers(self):
        root = Path(settings.BASE_DIR) / "templates"
        offenders = []
        for path in sorted(root.rglob("*.html")):
            rel = path.relative_to(root)
            if rel.parts[0] == "admin":  # Django-admin override is served with a relaxed CSP
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"\sstyle\s*=", text) or re.search(r"""\son[a-z]+\s*=\s*["']""", text):
                offenders.append(rel.as_posix())
        self.assertEqual(offenders, [], f"Inline style=/on*= is blocked by the CSP: {offenders}")


class PeriodDashboardTests(BaseData):
    """Collected / outstanding / charts follow the period chosen in the picker."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.today = timezone.localdate()
        plan = FeePlan.objects.create(
            academy=self.ac, name="Monthly", plan_type=PlanType.FIXED_MONTHLY,
            period=Period.MONTHLY, amount=Decimal("1000"),
        )
        _, self.inv1 = fee_services.assign_fee(self.s1, self.cricket, plan, actor=self.admin)
        _, self.inv2 = fee_services.assign_fee(self.s2, self.cricket, plan, actor=self.admin)
        fee_services.record_manual_payment(self.inv1, Decimal("1000"), PaymentMethod.CASH, self.admin)
        fee_services.record_manual_payment(self.inv2, Decimal("400"), PaymentMethod.UPI, self.admin)
        # Move the second payment into last year's March.
        last_year = self.today.year - 1
        Payment.objects.filter(invoice=self.inv2).update(
            recorded_at=timezone.make_aware(datetime(last_year, 3, 15, 10, 0))
        )
        self.last_year = last_year

    def get(self, query=""):
        res = self.client.get("/app/admin/" + query)
        self.assertEqual(res.status_code, 200)
        return res

    def test_default_is_current_month(self):
        res = self.get()
        self.assertEqual(res.context["period"].value, f"{self.today:%Y-%m}")
        self.assertEqual(res.context["summary"]["collected"], Decimal("1000.00"))

    def test_month_filters_collected(self):
        res = self.get(f"?period={self.last_year}-03")
        self.assertEqual(res.context["summary"]["collected"], Decimal("400.00"))
        self.assertEqual(len(res.context["recent_payments"]), 1)

    def test_year_filters_collected(self):
        res = self.get(f"?period={self.last_year}")
        self.assertTrue(res.context["period"].is_year)
        self.assertEqual(res.context["summary"]["collected"], Decimal("400.00"))
        self.assertIn(f"Jan – Dec {self.last_year}", res.content.decode())

    def test_outstanding_is_unpaid_balance_due_by_period_end(self):
        # inv2 still owes 600 (inv1 is fully paid); pin its due date to this month.
        self.inv2.due_date = self.today.replace(day=1)
        self.inv2.save(update_fields=["due_date"])
        res = self.get(f"?period={self.today:%Y-%m}")
        self.assertEqual(res.context["summary"]["outstanding"], Decimal("600.00"))
        res = self.get(f"?period={self.last_year}")  # nothing was due back then
        self.assertEqual(res.context["summary"]["outstanding"], Decimal("0"))
        res = self.get(f"?period={self.today.year}")  # year view includes it
        self.assertEqual(res.context["summary"]["outstanding"], Decimal("600.00"))

    def test_picker_lists_months_from_first_payment_only(self):
        res = self.get()
        values = [m.value for m in res.context["month_options"]]
        self.assertEqual(values[0], f"{self.today:%Y-%m}")
        self.assertEqual(values[-1], f"{self.last_year}-03")  # first payment month
        self.assertEqual([y.value for y in res.context["year_options"]], [str(self.today.year), str(self.last_year)])

    def test_bad_or_future_period_falls_back_to_current_month(self):
        for q in ("?period=junk", "?period=2026-13", f"?period={self.today.year + 1}-01"):
            self.assertEqual(self.get(q).context["period"].value, f"{self.today:%Y-%m}")

    def test_revenue_csv_respects_period(self):
        res = self.client.get(f"/app/reports/revenue.csv?period={self.last_year}-03")
        body = res.content.decode()
        self.assertEqual(body.strip().count("\n"), 1)  # header + one row
        self.assertIn(f'revenue_{self.last_year}-03_', res["Content-Disposition"])
        all_rows = self.client.get("/app/reports/revenue.csv").content.decode()
        self.assertEqual(all_rows.strip().count("\n"), 2)


class PeriodParsingTests(SimpleTestCase):
    today = date(2026, 10, 4)

    def test_month(self):
        p = periods.parse_period("2026-02", self.today)
        self.assertEqual((p.start, p.end), (date(2026, 2, 1), date(2026, 2, 28)))
        self.assertEqual(p.label, "Feb 2026")
        self.assertEqual(p.range_label, "01 Feb – 28 Feb 2026")

    def test_year(self):
        p = periods.parse_period("2025", self.today)
        self.assertEqual((p.start, p.end, p.label), (date(2025, 1, 1), date(2025, 12, 31), "2025"))

    def test_fallbacks(self):
        for raw in (None, "", "abc", "2026-00", "2026-13", "2026-11", "2027", "1999"):
            self.assertEqual(periods.parse_period(raw, self.today).value, "2026-10", raw)

    def test_options_start_at_first_payment(self):
        # No payments yet (or first payment this month): only the current month / year.
        self.assertEqual([m.value for m in periods.month_options(self.today)], ["2026-10"])
        self.assertEqual([m.value for m in periods.month_options(self.today, date(2026, 10, 2))], ["2026-10"])
        self.assertEqual([y.value for y in periods.year_options(self.today)], ["2026"])
        # First payment in August: Oct, Sep, Aug — nothing earlier.
        self.assertEqual(
            [m.value for m in periods.month_options(self.today, date(2026, 8, 20))],
            ["2026-10", "2026-09", "2026-08"],
        )
        self.assertEqual(len(periods.month_options(self.today, date(2024, 1, 5))), 34)
        self.assertEqual([y.value for y in periods.year_options(self.today, date(2024, 1, 5))], ["2026", "2025", "2024"])


class NotificationPageTests(BaseData):
    def setUp(self):
        super().setUp()
        from apps.notifications.models import Notification

        self.Notification = Notification
        self.mine = Notification.objects.create(recipient=self.admin, title="Fee due", url="/app/fees/")
        self.other = Notification.objects.create(recipient=self.p1, title="Not yours")
        self.client.force_login(self.admin)

    def test_page_has_no_heading_and_no_open_button(self):
        html = self.client.get("/app/notifications/").content.decode()
        self.assertNotIn("<h1>Notifications</h1>", html)
        self.assertNotIn("Open →", html)
        self.assertIn(f'action="/app/notifications/{self.mine.pk}/dismiss/"', html)
        self.assertIn('class="btn-x"', html)

    def test_dismiss_removes_own_notification(self):
        res = self.client.post(f"/app/notifications/{self.mine.pk}/dismiss/")
        self.assertRedirects(res, "/app/notifications/")
        self.assertFalse(self.Notification.objects.filter(pk=self.mine.pk).exists())

    def test_dismiss_via_fetch_returns_unread_count(self):
        res = self.client.post(f"/app/notifications/{self.mine.pk}/dismiss/", HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(res.json(), {"ok": True, "unread": 0})

    def test_cannot_dismiss_someone_elses_or_via_get(self):
        self.assertEqual(self.client.post(f"/app/notifications/{self.other.pk}/dismiss/").status_code, 404)
        self.assertEqual(self.client.get(f"/app/notifications/{self.mine.pk}/dismiss/").status_code, 405)
        self.assertTrue(self.Notification.objects.filter(pk__in=[self.mine.pk, self.other.pk]).count() == 2)


class SidebarTests(BaseData):
    def test_account_links_moved_out_of_sidebar(self):
        for user, home in ((self.admin, "/app/admin/"), (self.p1, "/app/parent/")):
            self.client.force_login(user)
            html = self.client.get(home).content.decode()
            self.assertNotIn('<div class="nav-group">Account</div>', html)
            self.assertNotIn("</span> Notifications", html)
            self.assertNotIn("</span> Profile", html)
            self.assertIn('class="user-chip" href="/app/profile/"', html)       # profile via the name chip
            self.assertIn('class="icon-btn bell-btn" aria-label="Notifications"', html)  # grey bell
            self.assertNotIn("🔔", html)

    def test_batches_live_under_branches(self):
        self.client.force_login(self.admin)
        html = self.client.get("/app/admin/").content.decode()
        self.assertNotIn("</span> Batches</a>", html)
        self.assertNotIn('href="/app/admin/batches/"', html)
        # batch pages highlight Branches and lead back to the branch's Batches tab
        res = self.client.get(f"/app/admin/batches/{self.batch1.pk}/edit/")
        back = f"/app/admin/branches/{self.batch1.branch_id}/?tab=batches"
        self.assertEqual(res.context["back_url"], back)
        self.assertIn('class="nav-link active" href="/app/admin/branches/"', res.content.decode())
        data = {"branch": self.batch1.branch_id, "sport": self.batch1.sport_id, "name": "Batch1",
                "days": ["Mon"], "start_time": "", "end_time": "", "capacity": 20, "is_active": "on"}
        self.assertRedirects(self.client.post(f"/app/admin/batches/{self.batch1.pk}/edit/", data), back)


class LivePageTests(BaseData):
    def test_live_page_is_a_full_height_table_without_heading(self):
        self.client.force_login(self.admin)
        html = self.client.get("/app/live/").content.decode()
        self.assertNotIn("running a session", html)
        self.assertIn('<main class="content content-fill">', html)
        self.assertIn('class="card fill-card"', html)
        for hook in ('id="liveData"', 'id="liveAsOf"', 'id="liveCount"'):  # used by app.js polling
            self.assertIn(hook, html)
        # live count + "Updated" sit above the table; only the auto-refresh note is below it
        self.assertLess(html.index('id="liveCount"'), html.index('id="liveData"'))
        self.assertLess(html.index('id="liveAsOf"'), html.index('id="liveData"'))
        foot = html[html.index('class="small muted live-foot"'):]
        self.assertIn("Auto-refreshes every few seconds", foot)
        self.assertNotIn("liveAsOf", foot)
        self.assertNotIn("liveCount", foot)


class LiveRowMenuTests(BaseData):
    """Each live-session row carries its own ⋮ (more_vert) menu items, by role."""

    def setUp(self):
        super().setUp()
        from apps.attendance.models import Session, SessionStatus

        self.coach.phone = "+91 98765 43210"
        self.coach.save(update_fields=["phone"])
        self.session = Session.objects.create(
            batch=self.batch1, date=timezone.localdate(), status=SessionStatus.LIVE,
            coach=self.coach, start_at=timezone.now(),
        )

    def actions(self, user):
        self.client.force_login(user)
        rows = self.client.get("/app/live/data/").json()["sessions"]
        self.assertEqual(len(rows), 1)
        return {a["label"]: a["url"] for a in rows[0]["actions"]}

    def test_admin_menu(self):
        acts = self.actions(self.admin)
        self.assertEqual(acts["View attendance"], f"/app/coach/session/{self.session.pk}/attendance/")
        self.assertEqual(acts["Edit batch"], f"/app/admin/batches/{self.batch1.pk}/edit/")
        self.assertEqual(acts["Call coach"], "tel:+919876543210")
        self.assertEqual(acts["Email coach"], "mailto:c@a.com")

    def test_manager_menu_only_has_contact_actions(self):
        acts = self.actions(self.mgr)  # admin-only pages are not offered to managers
        self.assertEqual(set(acts), {"Call coach", "Email coach"})


class BranchesPageTests(BaseData):
    """Branches: photo-card grid (list) → one branch's page (overview / batches)."""

    def setUp(self):
        super().setUp()
        self.b1.address = "Auroville Road, Puducherry"
        self.b1.save(update_fields=["address"])
        self.b1.sports.add(self.cricket)
        self.b2.is_active = False
        self.b2.save(update_fields=["is_active"])
        self.client.force_login(self.admin)

    def get(self, url):
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        return res

    def test_grid_shows_a_card_per_branch(self):
        res = self.get("/app/admin/branches/")
        html = res.content.decode()
        self.assertEqual([b.name for b in res.context["branches"]], ["B1", "B2"])
        self.assertIn('class="branch-card" href="/app/admin/branches/%d/"' % self.b1.id, html)
        self.assertIn("Auroville Road, Puducherry", html)
        self.assertIn("🏏", html)  # cover art from the branch's sport when there is no photo

    def test_grid_search_and_status_filters(self):
        names = lambda url: [b.name for b in self.get(url).context["branches"]]
        self.assertEqual(names("/app/admin/branches/?q=auroville"), ["B1"])
        self.assertEqual(names("/app/admin/branches/?status=inactive"), ["B2"])
        self.assertEqual(names("/app/admin/branches/?status=active"), ["B1"])

    def test_old_branch_links_redirect(self):
        res = self.client.get(f"/app/admin/branches/?branch={self.b2.id}")
        self.assertRedirects(res, f"/app/admin/branches/{self.b2.id}/")

    def test_branch_page_overview_and_batches(self):
        res = self.get(f"/app/admin/branches/{self.b1.id}/")
        self.assertEqual(res.context["selected"], self.b1)
        html = res.content.decode()
        for text in ("Basic Information", "Sports Offered", "Managers", '<span class="chip-lg">Cricket</span>', "Mgr"):
            self.assertIn(text, html)
        # only this branch, full page: no list of other branches; back link to the grid
        self.assertNotIn(f'href="/app/admin/branches/{self.b2.id}/"', html)
        self.assertIn('<a class="back-link" href="/app/admin/branches/">← All branches</a>', html)
        res = self.get(f"/app/admin/branches/{self.b2.id}/?tab=batches")
        self.assertEqual(list(res.context["batches"]), [self.batch2])
        self.assertIn(f"/app/admin/batches/{self.batch2.id}/edit/", res.content.decode())

    def test_students_tab_lists_students_enrolled_at_the_branch(self):
        res = self.get(f"/app/admin/branches/{self.b1.id}/?tab=students")
        self.assertEqual(list(res.context["students"]), [self.s1])  # s2 is at B2
        html = res.content.decode()
        self.assertIn(f'href="/app/students/{self.s1.id}/"', html)
        self.assertIn("Cricket · Batch1", html)
        Enrollment.objects.filter(student=self.s1, branch=self.b1).update(status="WITHDRAWN")
        self.assertEqual(list(self.get(f"/app/admin/branches/{self.b1.id}/?tab=students").context["students"]), [])

    def test_branch_page_404_for_unknown(self):
        self.assertEqual(self.client.get("/app/admin/branches/99999/").status_code, 404)

    def _edit(self, **extra):
        data = {"name": "B2", "code": "", "address": "", "latitude": "", "longitude": "",
                "geofence_radius_m": 200, "phone": "", "sports": [self.cricket.id], "is_active": "on"}
        data.update(extra)
        return self.client.post(f"/app/admin/branches/{self.b2.id}/edit/", data)

    def test_edit_sits_in_the_more_menu(self):
        html = self.get(f"/app/admin/branches/{self.b2.id}/").content.decode()
        self.assertNotIn("✏️ Edit</a>", html)                       # no exposed Edit button
        menu = html[html.index('<details class="dropdown more-menu detail-menu">'):]
        menu = menu[:menu.index("</details>")]
        self.assertIn('class="kebab-btn kebab-md"', menu)
        self.assertIn(f'href="/app/admin/branches/{self.b2.id}/edit/"', menu)
        self.assertIn("Edit branch", menu)

    def test_add_buttons_are_highlighted(self):
        batches = self.get(f"/app/admin/branches/{self.b2.id}/?tab=batches").content.decode()
        self.assertIn(f'class="btn btn-sm btn-primary" href="/app/admin/batches/new/?branch={self.b2.id}">＋ New batch', batches)
        students = self.get(f"/app/admin/branches/{self.b2.id}/?tab=students").content.decode()
        self.assertIn('class="btn btn-sm btn-primary" href="/app/students/new/">＋ Add student', students)

    def test_edit_returns_to_the_branch_page(self):
        self.assertRedirects(self._edit(), f"/app/admin/branches/{self.b2.id}/")

    def test_new_batch_preselects_branch(self):
        res = self.client.get(f"/app/admin/batches/new/?branch={self.b2.id}")
        self.assertEqual(res.context["form"]["branch"].value(), self.b2.id)


class BranchPhotoTests(BaseData):
    def setUp(self):
        super().setUp()
        import tempfile

        self.media = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.media, True)
        self.client.force_login(self.admin)

    def _png(self, name="cover.png", size=(40, 20)):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", size, (30, 140, 80)).save(buf, "PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def _post(self, photo, **extra):
        data = {"name": "B1", "code": "", "address": "", "latitude": "", "longitude": "",
                "geofence_radius_m": 200, "phone": "", "is_active": "on", "photo": photo}
        data.update(extra)
        return self.client.post(f"/app/admin/branches/{self.b1.id}/edit/", data)

    def test_upload_shows_on_grid_and_replace_removes_old_file(self):
        from django.test import override_settings

        with override_settings(MEDIA_ROOT=self.media):
            self.assertEqual(self._post(self._png()).status_code, 302)
            self.b1.refresh_from_db()
            first = self.b1.photo.name
            self.assertTrue(first.startswith("branches/") and first.endswith(".png"))
            html = self.client.get("/app/admin/branches/").content.decode()
            self.assertIn(f'src="/media/{first}"', html)
            self._post(self._png("new.png"))
            self.b1.refresh_from_db()
            self.assertNotEqual(self.b1.photo.name, first)
            self.assertFalse(self.b1.photo.storage.exists(first))

    def test_rejects_non_images(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        with override_settings(MEDIA_ROOT=self.media):
            res = self._post(SimpleUploadedFile("notes.png", b"not really an image", content_type="image/png"))
            self.assertEqual(res.status_code, 200)  # form re-rendered with an error
            self.assertTrue(res.context["form"].errors.get("photo"))
            res = self._post(self._png("anim.gif"))
            self.assertIn("Use a JPG, PNG or WebP image.", res.context["form"].errors.get("photo", []))


class BranchFeesTabTests(BaseData):
    """Branch page → Fees tab: the dashboard's three tiles, for that branch only."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        plan = FeePlan.objects.create(
            academy=self.ac, name="Monthly", plan_type=PlanType.FIXED_MONTHLY,
            period=Period.MONTHLY, amount=Decimal("1000"),
        )
        _, inv1 = fee_services.assign_fee(self.s1, self.cricket, plan, actor=self.admin)  # B1
        _, inv2 = fee_services.assign_fee(self.s2, self.cricket, plan, actor=self.admin)  # B2
        fee_services.record_manual_payment(inv1, Decimal("700"), PaymentMethod.CASH, self.admin)
        fee_services.record_manual_payment(inv2, Decimal("1000"), PaymentMethod.CASH, self.admin)
        for inv in (inv1, inv2):  # make both due inside the current month
            inv.due_date = timezone.localdate().replace(day=1)
            inv.save(update_fields=["due_date"])

    def _fees(self, branch, query=""):
        res = self.client.get(f"/app/admin/branches/{branch.id}/?tab=fees{query}")
        self.assertEqual(res.status_code, 200)
        return res

    def test_tiles_show_only_this_branch(self):
        res = self._fees(self.b1)
        self.assertEqual(res.context["summary"]["collected"], Decimal("700.00"))   # not B2's 1000
        self.assertEqual(res.context["summary"]["outstanding"], Decimal("300.00"))
        html = res.content.decode()
        for label in ("Collected", "Outstanding"):
            self.assertIn(f'<div class="kpi-label">{label}</div>', html)
        self.assertNotIn('<div class="kpi-label">Students</div>', html)
        self.assertNotIn("kpi-link", html)  # tiles are plain numbers now, not switches

    def test_single_table_lists_paid_and_unpaid(self):
        res = self._fees(self.b1)  # default filter: All
        self.assertEqual(res.context["show"], "all")
        rows = [(r["paid"], r["student"], r["amount"]) for r in res.context["fee_rows"]]
        self.assertEqual(rows, [(True, self.s1, Decimal("700.00")), (False, self.s1, Decimal("300.00"))])
        html = res.content.decode()
        self.assertEqual(html.count('<table class="data fee-table">'), 1)
        self.assertIn("Total collected", html)
        self.assertIn("Total outstanding", html)

    def test_filter_paid_and_unpaid(self):
        summary = self._fees(self.b1).context["summary"]
        paid = self._fees(self.b1, "&show=paid").context["fee_rows"]
        self.assertTrue(paid and all(r["paid"] for r in paid))
        self.assertEqual(sum(r["amount"] for r in paid), summary["collected"])
        unpaid = self._fees(self.b1, "&show=unpaid").context["fee_rows"]
        self.assertTrue(unpaid and not any(r["paid"] for r in unpaid))
        self.assertEqual(sum(r["amount"] for r in unpaid), summary["outstanding"])
        # B2's student paid in full, so B2 has nobody unpaid
        res = self._fees(self.b2, "&show=unpaid")
        self.assertEqual(res.context["fee_rows"], [])
        self.assertIn("Everyone at this branch has paid", res.content.decode())
        # unknown values fall back to All; links from the old tile switch still land right
        self.assertEqual(self._fees(self.b1, "&show=nope").context["show"], "all")
        self.assertEqual(self._fees(self.b1, "&view=outstanding").context["show"], "unpaid")

    def test_filter_links_and_period_picker_keep_each_other(self):
        month = f"{timezone.localdate():%Y-%m}"
        html = self._fees(self.b1, "&show=unpaid").content.decode()
        self.assertIn(f'href="?tab=fees&amp;period={month}"', html)                    # All
        self.assertIn(f'href="?tab=fees&amp;period={month}&amp;show=paid"', html)
        self.assertIn(f'<a class="seg-opt is-active" href="?tab=fees&amp;period={month}&amp;show=unpaid" aria-current="true">Unpaid<span class="seg-count">1</span></a>', html)
        self.assertIn(f'href="?tab=fees&amp;show=unpaid&amp;period={month}"', html)    # period options keep the filter

    def test_period_param(self):
        last_year = timezone.localdate().year - 1
        res = self.client.get(f"/app/admin/branches/{self.b1.id}/?tab=fees&period={last_year}")
        self.assertTrue(res.context["period"].is_year)
        self.assertEqual(res.context["summary"]["collected"], Decimal("0"))
