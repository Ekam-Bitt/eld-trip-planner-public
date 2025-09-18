from django.urls import path

from .views import DashboardView, LoginView, LogoutView, MeView, ProfileUpdateView, SignupView

app_name = "drivers"

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("profile/", ProfileUpdateView.as_view(), name="profile-update"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
