"""
Seed a realistic demo academy so the whole ERP is explorable immediately.

    python manage.py seed_demo --reset

In DEBUG, sign in as any seeded email — the OTP is shown on the login screen
and printed to the runserver console.
"""
import random
from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.academy.models import (
    Academy,
    Batch,
    Branch,
    CoachAssignment,
    ManagerAssignment,
    Sport,
)
from apps.accounts.models import Role
from apps.attendance.models import (
    Attendance,
    AttendanceStatus,
    CheckInMethod,
    Session,
    SessionStatus,
)
from apps.fees import services as fee_services
from apps.fees.models import FeePlan, Invoice, PaymentMethod, Period, PlanType
from apps.students.models import Enrollment, Guardian, Student

User = get_user_model()

ADMIN_EMAIL = "adiseelansri@gmail.com"
ADMIN_PASSWORD = "Champion@Admin1"  # for /admin/ ; OTP is used for the portal


class Command(BaseCommand):
    help = "Seed a demo multi-sport academy with data across all four roles."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(42)
        if opts["reset"]:
            self._reset()

        if Academy.objects.filter(slug="champions-academy").exists():
            self.stdout.write(self.style.WARNING(
                "Demo academy already exists. Re-run with --reset to rebuild."))
            return

        academy = Academy.objects.create(
            name="Champions Multi-Sport Academy",
            slug="champions-academy",
            contact_email="hello@champions.example",
            contact_phone="+91 90000 00000",
            currency="INR",
        )
        self.stdout.write(self.style.SUCCESS(f"Academy: {academy.name}"))

        # ---- Sports ------------------------------------------------
        sport_names = ["Cricket", "Football", "Swimming", "Badminton", "Tennis"]
        sports = {n: Sport.objects.create(academy=academy, name=n) for n in sport_names}

        # ---- Admin -------------------------------------------------
        admin = User.objects.filter(email=ADMIN_EMAIL).first()
        if admin is None:
            admin = User.objects.create_superuser(
                email=ADMIN_EMAIL, password=ADMIN_PASSWORD, full_name="Adi (Owner)"
            )
        admin.role = Role.ADMIN
        admin.academy = academy
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()

        # ---- Branches (Puducherry-area coordinates) ----------------
        branches = []
        branch_defs = [
            ("Central Court", "White Town, Puducherry", 11.9340, 79.8300, ["Cricket", "Badminton", "Tennis"]),
            ("Beachside Arena", "Auroville Road, Puducherry", 11.9975, 79.8100, ["Football", "Swimming", "Cricket"]),
            ("Uptown Hub", "Lawspet, Puducherry", 11.9600, 79.8000, ["Badminton", "Football", "Tennis"]),
        ]
        for name, addr, lat, lng, bsports in branch_defs:
            b = Branch.objects.create(
                academy=academy, name=name, code=name[:3].upper(), address=addr,
                latitude=lat, longitude=lng, geofence_radius_m=250,
                phone="+91 91000 0000" + str(len(branches)),
            )
            b.sports.set([sports[s] for s in bsports])
            branches.append(b)
        self.stdout.write(self.style.SUCCESS(f"Branches: {len(branches)}"))

        # ---- Managers ----------------------------------------------
        managers = []
        for i, (name, assigned) in enumerate([
            ("Priya Nair", [0, 1]),
            ("Ravi Kumar", [2]),
        ], start=1):
            m = User.objects.create_user(
                email=f"manager{i}@demo.local", full_name=name,
                role=Role.MANAGER, academy=academy, phone=f"+9199888800{i}",
            )
            for bi in assigned:
                ManagerAssignment.objects.create(manager=m, branch=branches[bi], assigned_by=admin)
            managers.append(m)
        self.stdout.write(self.style.SUCCESS(f"Managers: {len(managers)}"))

        # ---- Coaches -----------------------------------------------
        coaches = []
        coach_names = ["Arjun Rao", "Meena Das", "Sundar Raj", "Kavya Iyer"]
        for i, name in enumerate(coach_names, start=1):
            c = User.objects.create_user(
                email=f"coach{i}@demo.local", full_name=name,
                role=Role.COACH, academy=academy, phone=f"+9199777700{i}",
            )
            coaches.append(c)

        # ---- Batches -----------------------------------------------
        all_days = ["Mon", "Wed", "Fri", "Tue", "Thu", "Sat"]
        batches = []
        for b in branches:
            for sport in b.sports.all():
                batch = Batch.objects.create(
                    branch=b, sport=sport, name=random.choice(["U-12 Morning", "U-14 Evening", "Junior Batch", "Elite Squad"]),
                    days_of_week=",".join(random.sample(all_days, 3)),
                    start_time=time(random.choice([6, 16, 17]), 0),
                    end_time=time(random.choice([8, 18, 19]), 0),
                    capacity=30,
                )
                # assign 1-2 coaches
                for c in random.sample(coaches, random.choice([1, 2])):
                    CoachAssignment.objects.get_or_create(coach=c, batch=batch, defaults={"assigned_by": admin})
                batches.append(batch)
        self.stdout.write(self.style.SUCCESS(f"Coaches: {len(coaches)} · Batches: {len(batches)}"))

        # ---- Fee plans ---------------------------------------------
        plans = []
        plans.append(FeePlan.objects.create(academy=academy, name="Standard Monthly", plan_type=PlanType.FIXED_MONTHLY, period=Period.MONTHLY, amount=Decimal("1500")))
        plans.append(FeePlan.objects.create(academy=academy, name="Quarterly Package", plan_type=PlanType.PACKAGE, period=Period.QUARTERLY, amount=Decimal("4000")))
        plans.append(FeePlan.objects.create(academy=academy, name="Annual Package", plan_type=PlanType.PACKAGE, period=Period.YEARLY, amount=Decimal("14000")))
        plans.append(FeePlan.objects.create(academy=academy, name="Swimming Monthly", sport=sports["Swimming"], plan_type=PlanType.FIXED_MONTHLY, period=Period.MONTHLY, amount=Decimal("2000")))

        # ---- Students + parents + enrollments + fees ---------------
        first = ["Aarav", "Diya", "Vihaan", "Anika", "Kabir", "Sara", "Reyansh", "Ira", "Arnav", "Myra", "Vivaan", "Aadhya"]
        last = ["Sharma", "Menon", "Reddy", "Nair", "Gupta", "Pillai"]
        students = []
        today = timezone.localdate()
        for i in range(12):
            name = f"{first[i]} {random.choice(last)}"
            s = Student.objects.create(
                academy=academy, full_name=name,
                date_of_birth=today.replace(year=today.year - random.randint(8, 15)),
                gender=random.choice(["M", "F"]), contact_phone=f"+9199666600{i:02d}",
                created_by=admin,
            )
            # parent
            parent = User.objects.create_user(
                email=f"parent{i+1}@demo.local", full_name=f"{random.choice(['Mr','Mrs'])}. {name.split()[1]}",
                role=Role.PARENT, academy=academy, phone=f"+9199555500{i:02d}",
            )
            Guardian.objects.create(parent=parent, student=s, relationship="guardian", is_primary=True)

            # enroll into 1-2 batches
            for batch in random.sample(batches, random.choice([1, 2])):
                Enrollment.objects.get_or_create(
                    student=s, batch=batch,
                    defaults={"sport": batch.sport, "branch": batch.branch, "created_by": admin},
                )
                plan = random.choice(plans)
                if plan.sport and plan.sport != batch.sport:
                    plan = plans[0]
                fee, invoice = fee_services.assign_fee(
                    s, batch.sport, plan, start_date=today - timedelta(days=random.randint(1, 40)), actor=admin
                )
                self._vary_invoice_state(invoice, admin)
            students.append(s)
        self.stdout.write(self.style.SUCCESS(f"Students: {len(students)} (+ parents)"))

        # ---- Sessions & attendance (history + one live) ------------
        self._seed_sessions(batches, coaches, students, admin)

        # ---- Flag overdue (fires reminders) ------------------------
        flagged = fee_services.flag_overdue(academy=academy)

        self._summary(flagged)

    # ------------------------------------------------------------------
    def _vary_invoice_state(self, invoice, admin):
        r = random.random()
        if r < 0.4:  # fully paid
            fee_services.record_manual_payment(invoice, invoice.balance, PaymentMethod.UPI, admin, "Demo payment")
        elif r < 0.6:  # partial
            half = (invoice.balance / 2).quantize(Decimal("0.01"))
            fee_services.record_manual_payment(invoice, half, PaymentMethod.CASH, admin, "Part payment")
        elif r < 0.8:  # overdue (backdate)
            invoice.issued_date = timezone.localdate() - timedelta(days=40)
            invoice.due_date = timezone.localdate() - timedelta(days=25)
            invoice.save(update_fields=["issued_date", "due_date"])
            invoice.recompute()
        # else: leave as due

    def _seed_sessions(self, batches, coaches, students, admin):
        now = timezone.now()
        # Past completed sessions with attendance
        for batch in batches:
            roster = list(
                Student.objects.filter(enrollments__batch=batch).distinct()
            )
            if not roster:
                continue
            coach = batch.coaches.first() or random.choice(coaches)
            for d in range(1, random.randint(3, 6)):
                day = (now - timedelta(days=d)).date()
                session, created = Session.objects.get_or_create(batch=batch, date=day)
                if not created:
                    continue
                start = now - timedelta(days=d, hours=2)
                session.status = SessionStatus.COMPLETED
                session.coach = coach
                session.check_in_method = CheckInMethod.GEO
                session.check_in_at = start
                session.start_at = start
                session.end_at = start + timedelta(hours=1)
                session.check_in_distance_m = random.randint(10, 200)
                session.save()
                for st in roster:
                    Attendance.objects.create(
                        session=session, student=st, marked_by=coach,
                        status=random.choices(
                            [AttendanceStatus.PRESENT, AttendanceStatus.LATE, AttendanceStatus.ABSENT],
                            weights=[8, 1, 1])[0],
                    )

        # One LIVE session right now, so the live view has something to show.
        for batch in batches:
            if Student.objects.filter(enrollments__batch=batch).exists():
                coach = batch.coaches.first() or coaches[0]
                session, _ = Session.objects.get_or_create(batch=batch, date=timezone.localdate())
                session.status = SessionStatus.LIVE
                session.coach = coach
                session.check_in_method = CheckInMethod.GEO
                session.check_in_at = now
                session.start_at = now
                session.check_in_distance_m = 42
                session.save()
                break

    def _reset(self):
        self.stdout.write(self.style.WARNING("Resetting demo data…"))
        Academy.objects.filter(slug="champions-academy").delete()
        # Remove seeded demo users (keep the owner account, drop role/academy link).
        User.objects.filter(email__endswith="@demo.local").delete()

    def _summary(self, flagged):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(" DEMO READY"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f" Invoices flagged overdue: {flagged}")
        self.stdout.write("")
        self.stdout.write(" Sign in at /auth/login/ with any of these emails.")
        self.stdout.write(" In DEBUG the OTP is shown on screen + printed here.")
        self.stdout.write("")
        self.stdout.write(f"   ADMIN    : {ADMIN_EMAIL}")
        self.stdout.write("   MANAGER  : manager1@demo.local / manager2@demo.local")
        self.stdout.write("   COACH    : coach1@demo.local … coach4@demo.local")
        self.stdout.write("   PARENT   : parent1@demo.local … parent12@demo.local")
        self.stdout.write("")
        self.stdout.write(f"   Django /admin/ : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        self.stdout.write(self.style.SUCCESS("=" * 60))
