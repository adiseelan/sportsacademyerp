from django.urls import path

from .views import common, coach, dashboards, fees, manage, parent, reports, students

app_name = "portal"

urlpatterns = [
    path("", common.home, name="home"),

    # Notifications & profile
    path("notifications/", common.notifications_list, name="notifications"),
    path("notifications/<int:pk>/read/", common.notification_read, name="notification_read"),
    path("notifications/<int:pk>/dismiss/", common.notification_dismiss, name="notification_dismiss"),
    path("notifications/read-all/", common.notifications_read_all, name="notifications_read_all"),
    path("profile/", common.profile, name="profile"),

    # Live view (Admin/Manager)
    path("live/", common.live_page, name="live"),
    path("live/data/", common.live_json, name="live_json"),

    # Admin
    path("admin/", dashboards.admin_dashboard, name="admin_dashboard"),
    path("admin/branches/", dashboards.branches_list, name="branches"),
    path("admin/branches/<int:pk>/", dashboards.branch_detail, name="branch_detail"),
    path("admin/branches/new/", manage.branch_create, name="branch_create"),
    path("admin/branches/<int:pk>/edit/", manage.branch_edit, name="branch_edit"),
    path("admin/sports/new/", manage.sport_create, name="sport_create"),
    path("admin/batches/", manage.batch_list, name="batch_list"),
    path("admin/batches/new/", manage.batch_create, name="batch_create"),
    path("admin/batches/<int:pk>/edit/", manage.batch_edit, name="batch_edit"),
    path("admin/coaches/", dashboards.coaches_list, name="coaches"),
    path("admin/coaches/new/", manage.coach_create, name="coach_create"),
    path("admin/coaches/<int:pk>/assign/", manage.coach_assign, name="coach_assign"),
    path("admin/managers/", dashboards.managers_list, name="managers"),
    path("admin/managers/new/", manage.manager_create, name="manager_create"),
    path("admin/managers/<int:pk>/assign/", manage.manager_assign, name="manager_assign"),
    path("admin/audit/", common.audit_log, name="audit_log"),

    # Manager
    path("manager/", dashboards.manager_dashboard, name="manager_dashboard"),

    # Students (Admin/Manager)
    path("students/", students.student_list, name="student_list"),
    path("students/new/", students.student_create, name="student_create"),
    path("students/<int:pk>/", students.student_detail, name="student_detail"),
    path("students/<int:pk>/enroll/", students.student_enroll, name="student_enroll"),
    path("students/<int:pk>/assign-fee/", students.student_assign_fee, name="student_assign_fee"),

    # Fees
    path("fees/", fees.fee_status, name="fee_status"),
    path("fees/invoice/<int:pk>/", fees.invoice_detail, name="invoice_detail"),
    path("fees/invoice/<int:pk>/pay/", fees.record_payment, name="record_payment"),
    path("fees/invoice/<int:pk>/waive/", fees.waive_invoice, name="waive_invoice"),
    path("fees/invoice/<int:pk>/remind/", fees.send_reminder, name="send_reminder"),
    path("fees/invoice/<int:pk>/pay-online/", fees.pay_online, name="pay_online"),
    path("fees/invoice/<int:pk>/pay-online/confirm/", fees.confirm_online, name="confirm_online"),
    path("fees/receipt/<int:pk>/", fees.receipt, name="receipt"),

    # Coach
    path("coach/", coach.coach_today, name="coach_today"),
    path("coach/checkin/<int:batch_id>/", coach.coach_checkin, name="coach_checkin"),
    path("coach/session/<int:session_id>/attendance/", coach.coach_attendance, name="coach_attendance"),
    path("coach/history/", coach.coach_history, name="coach_history"),

    # Parent
    path("parent/", parent.parent_home, name="parent_home"),
    path("parent/fees/", parent.parent_fees, name="parent_fees"),
    path("parent/attendance/<int:student_id>/", parent.parent_attendance, name="parent_attendance"),

    # Reports (Admin/Manager)
    path("reports/", reports.reports_index, name="reports"),
    path("reports/revenue.csv", reports.export_revenue, name="export_revenue"),
    path("reports/outstanding.csv", reports.export_outstanding, name="export_outstanding"),
    path("reports/attendance.csv", reports.export_attendance, name="export_attendance"),
    path("reports/coach-activity.csv", reports.export_coach_activity, name="export_coach_activity"),
]
