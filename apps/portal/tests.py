from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.academy.models import Batch, Branch, CoachAssignment, ManagerAssignment, Sport
from apps.academy.scoping import accessible_students
from apps.accounts.models import Role, User
from apps.fees import services as fee_services
from apps.fees.models import FeePlan, InvoiceStatus, PaymentMethod, Period, PlanType
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
