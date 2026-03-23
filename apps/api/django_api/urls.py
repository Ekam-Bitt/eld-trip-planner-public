from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path("api/health", views.health),
    path("api/auth/signup", views.auth_signup),
    path("api/auth/login", views.auth_login),
    path("api/auth/logout", views.auth_logout),
    path("api/auth/me", views.auth_me),
    path("api/profile", views.profile_detail),
    path("api/fields", views.fields),
    path("api/trips/plan", views.trips_plan),
    path("api/trips/generate", views.trips_generate),
    path("api/logs/<str:record_id>/svg", views.log_svg),
    path("api/logs/<str:record_id>/svg/<str:filename>", views.log_svg),
    path("api/logs/<str:record_id>/pdf", views.log_pdf),
    path("api/logs/<str:record_id>/pdf/<str:filename>", views.log_pdf),
]
