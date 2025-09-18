"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", lambda request: HttpResponse("ok"), name="healthz"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="docs",
    ),
    path("api/drivers/", include("drivers.urls", namespace="drivers")),
    path("api/trips/", include("trips.urls", namespace="trips")),
    # Logs & inspections
    path(
        "api/logs/",
        include(
            (
                [
                    path(
                        "",
                        __import__("logs.views").views.LogEventCreateView.as_view(),
                        name="create",
                    ),
                    path(
                        "<int:trip_id>/",
                        __import__("logs.views").views.LogEventListView.as_view(),
                        name="list",
                    ),
                    path(
                        "<int:trip_id>/hos/",
                        __import__("logs.views").views.HOSSummaryView.as_view(),
                        name="hos",
                    ),
                    path(
                        "<int:trip_id>/daily/",
                        __import__("logs.views").views.DailyLogListView.as_view(),
                        name="daily-list",
                    ),
                    path(
                        "<int:trip_id>/daily/submit/",
                        __import__("logs.views").views.DailyLogSubmitView.as_view(),
                        name="daily-submit",
                    ),
                    path(
                        "<int:trip_id>/inspections/",
                        __import__("logs.views").views.InspectionListView.as_view(),
                        name="inspection-list",
                    ),
                    path(
                        "inspections/",
                        __import__("logs.views").views.InspectionCreateView.as_view(),
                        name="inspection-create",
                    ),
                ],
                "logs",
            ),
            namespace="logs",
        ),
    ),
    # Reports
    path(
        "api/reports/",
        include(
            (
                [
                    path(
                        "trip/<int:trip_id>/pdf/",
                        __import__("logs.views").views.TripReportPDFView.as_view(),
                        name="trip-pdf",
                    ),
                    path(
                        "trip/<int:trip_id>/csv/",
                        __import__("logs.views").views.TripReportCSVView.as_view(),
                        name="trip-csv",
                    ),
                ],
                "reports",
            ),
            namespace="reports",
        ),
    ),
]
