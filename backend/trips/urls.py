from django.urls import path

from .views import TripDetailView, TripListCreateView

app_name = "trips"

urlpatterns = [
    path("", TripListCreateView.as_view(), name="list-create"),
    path("<int:pk>/", TripDetailView.as_view(), name="detail"),
]
