from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_request, name="login"),
    path("verify/", views.login_verify, name="verify"),
    path("resend/", views.login_resend, name="resend"),
    path("logout/", views.logout_view, name="logout"),
]
