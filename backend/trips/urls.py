from django.urls import path

from .views import (
    SearchBoxRetrieveView,
    SearchBoxSuggestView,
    TripDetailView,
    TripListCreateView,
)

app_name = "trips"

urlpatterns = [
    path("", TripListCreateView.as_view(), name="list-create"),
    path("<int:pk>/", TripDetailView.as_view(), name="detail"),
    path("searchbox/suggest/", SearchBoxSuggestView.as_view(), name="searchbox-suggest"),
    path("searchbox/retrieve/", SearchBoxRetrieveView.as_view(), name="searchbox-retrieve"),
]
